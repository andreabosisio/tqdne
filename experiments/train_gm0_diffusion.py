# REF: https://github.com/dirmeier/dmvi

from tqdne.utils import *


from pathlib import Path
from absl import flags, app
from ml_collections import config_flags
from diffusers import DDIMScheduler, DDPMScheduler
from tqdne.conf import Config
from tqdne.consistency_model import LightningConsistencyModel
from tqdne.dataset import RepresentationDataset
from tqdne.diffusion import LightningDiffusion
from tqdne.plot import get_plots_list
from tqdne.metric import get_metrics_list
from tqdne.training import get_pl_trainer
from tqdne.unet import UNetModel
from torch.utils.data import DataLoader

import os
import logging
import multiprocessing

general_config = Config()

FLAGS = flags.FLAGS
config_flags.DEFINE_config_file("config", None, "training configuration", lock_config=False)
flags.DEFINE_bool("debug", False, "debug mode")
flags.DEFINE_bool("use_last_checkpoint", False, "get the last checkpoint from the output directory")
flags.DEFINE_string("checkpoint_file", None, "checkpoint file of the previously trained model")
flags.DEFINE_string("train_datapath", str(general_config.datasetdir / general_config.data_train), "path to the training data")
flags.DEFINE_string("test_datapath", str(general_config.datasetdir / general_config.data_test), "path to the test data")
flags.DEFINE_integer("downsampling_factor", 1, "downsampling factor")
flags.DEFINE_integer("max_amplitude", None, "maximum amplitude of the signals in the dataset")
flags.DEFINE_string("outdir", str(general_config.outputdir) , "out directory, i.e., place where results are written to")
flags.mark_flags_as_required(["config"])


def main(argv):
    del argv    

    # Read configuration parameters
    batch_size = FLAGS.config.optimizer_params.batch_size
    num_cond_features = len(general_config.features_keys)

    # Update configuration parameters based on the downsampling factor
    general_config.fs = general_config.fs // FLAGS.downsampling_factor
    # TODO: set signal length to the closest number having small factors
    general_config.signal_length = general_config.signal_length // FLAGS.downsampling_factor

    # Define the data representation
    data_representation = get_data_representation(FLAGS.config, signal_length=general_config.signal_length) 
    name = data_representation.get_name(FLAGS)
    data_repr_channels = data_representation.get_num_channels(general_config.num_channels)

    # Build UNet model
    logging.info("Build network...")
    net = UNetModel(in_channels=data_repr_channels, out_channels=data_repr_channels, cond_features=num_cond_features, **FLAGS.config.model.net_params)
    logging.info(f"Unet Params:\n  {FLAGS.config.model.net_params}")

    # Load the dataset
    train_dataset = RepresentationDataset(h5_path=Path(FLAGS.train_datapath), max_amplitude=FLAGS.max_amplitude, downsample=FLAGS.downsampling_factor, data_repr=data_representation) 
    test_dataset = RepresentationDataset(h5_path=Path(FLAGS.test_datapath), max_amplitude=FLAGS.max_amplitude, downsample=FLAGS.downsampling_factor, data_repr=data_representation)
    
    # DEBUG
    if FLAGS.debug:
        logging.info("DEBUG MODE: Using only a subset of the dataset")
        train_dataset = torch.utils.data.Subset(train_dataset, range(0, 1000))
        test_dataset = torch.utils.data.Subset(test_dataset, range(0, 200))
        logging.info(f"Train dataset size: {len(train_dataset)}")
        logging.info(f"Test dataset size: {len(test_dataset)}")
        batch_size = 32
        logging.info(f"DEBUG MODE: Decreasing the Batch Size to: {batch_size}")
        logging.info("DEBUG MODE: Not storing checkpoints")
        FLAGS.config.trainer_params.update({"enable_checkpointing": False})
        logging.info("DEBUG MODE: Not logging to wandb")
        FLAGS.config.trainer_params.update({"log_to_wandb": False})


    # Get the number of available CPU cores
    num_cores = multiprocessing.cpu_count()
    # Set the number of workers based on the number of CPU cores
    num_workers = num_cores - 1 if num_cores > 1 or FLAGS.debug else 0
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, num_workers=num_workers)

    if FLAGS.config.name == "consistency-model":
        logging.info("Build consistency model...")
        # TODO: what about the trainer and its parameters like max_epochs?
        model = LightningConsistencyModel(
            net, 
            lr=FLAGS.config.optimizer_params.lr, 
            example_input_array=[next(iter(train_loader))["repr"], torch.ones(batch_size), None, next(iter(train_loader))["cond"]],
            ml_config=FLAGS.config
        )
        FLAGS.config.trainer_params.update({"max_steps": FLAGS.config.trainer_params.max_epochs * len(train_loader)})
    elif FLAGS.config.name == "ddpm" or FLAGS.config.name == "ddim":
        logging.info("Build diffusion model...")
        if FLAGS.config.name == "ddpm":
            scheduler = DDPMScheduler(**FLAGS.config.model.scheduler_params)
        elif FLAGS.config.name == "ddim":
            timestep_decimation_factor = FLAGS.config.model.scheduler_params.timestep_decimation_factor
            del FLAGS.config.model.scheduler_params.timestep_decimation_factor
            scheduler = DDIMScheduler(**FLAGS.config.model.scheduler_params)
            FLAGS.config.model.scheduler_params.update({"num_inference_steps": FLAGS.config.model.scheduler_params.num_train_timesteps // timestep_decimation_factor})
            scheduler.set_timesteps(num_inference_steps=FLAGS.config.model.scheduler_params.num_inference_steps)
        else:
            raise ValueError(f"Unknown model name: {FLAGS.config.name}")    
        logging.info(f"Scheduler params: \n {scheduler.config}")
        logging.info("Build lightning module...")

        FLAGS.config.optimizer_params.update(
        {
            "n_train": len(train_dataset) // batch_size,
            "max_epochs": FLAGS.config.trainer_params.max_epochs,
        }
        )
        example_input_array = [next(iter(train_loader))["repr"], torch.randint(0, FLAGS.config.model.scheduler_params.num_train_timesteps,(batch_size,)).long(), None, next(iter(train_loader))["cond"]]
        model = LightningDiffusion(
            net,
            scheduler,
            prediction_type=FLAGS.config.model.scheduler_params.prediction_type,
            optimizer_params=FLAGS.config.optimizer_params,
            cond_signal_input=False,
            cond_input=True,
            example_input_array=example_input_array,
            ml_config=FLAGS.config
        )
    else:
        raise ValueError(f"Unknown model name: {FLAGS.config.name}")
    

    logging.info("Build Pytorch Lightning Trainer...")
    metrics = get_metrics_list(FLAGS.config.metrics, general_config, data_representation)
    trainer = get_pl_trainer(
        name=name,
        task="generation",
        val_loader=test_loader,
        metrics=metrics,
        plots=get_plots_list(FLAGS.config.plots, metrics, general_config, data_representation),
        flags=flags.FLAGS,
        **FLAGS.config.trainer_params,
    )

    logging.info("Start training...")
    if FLAGS.checkpoint_file is not None:
        checkpoint = Path(FLAGS.checkpoint_file)
    elif FLAGS.use_last_checkpoint:
        checkpoint = get_last_checkpoint(trainer.default_root_dir)    
    else:
        checkpoint = None  
     
    trainer.fit(
        model,
        train_dataloaders=train_loader,
        val_dataloaders=test_loader,
        ckpt_path=checkpoint
    )

    logging.info("Done!")

if __name__ == "__main__":
    app.run(main)    


