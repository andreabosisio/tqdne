# TQDNE: This Quake Does Not Exist

## About

This repository contains the experimental code of the thesis [On the Synthesis of Seismic Broadband Waveforms with Conditional Diffusion Models](https://www.politesi.polimi.it/handle/10589/227978).
It can be used to generate seismic waveforms, replicate the results from the manuscript, or for training custom models from scratch.

![Model scheme](imgs/scheme.png)

## Installation

You can install all required dependencies and the versions that have been used in the experiments by creating a new conda environment, and by then activating it:

```bash
conda env create -f environment.yaml 
conda activate tqdne
```

## Experiments

All experimental code can be found in `experiments` (which we, e.g., used to train the generative models).

