#URL = https://zenodo.org/api/records/13862601/files-archive

# Donwload the files in the 'outputs' folder
#curl -L $URL -o ../outputs/synthetic_datasets.zip

# Unzip the files
#unzip ../outputs/synthetic_datasets.zip -d ../outputs/

# Remove the zip file
#rm ../outputs/synthetic_datasets.zip

# List all the files in the 'outputs' folder recursively, and for each path containing a ".ckpt" file, take the associated .hdf5 file and move it in the folder of that '.ckpt' file
find ../outputs/ -type f | grep ".ckpt" | while read -r line; do
    printf "___________________________________________________\n"
    # Get the path of the ckpt file
    ckpt_path=$(dirname $line)
    printf "Processing $ckpt_path\n"
    # Get the name of the ckpt file (without the path and the extension)
    ckpt_filename=$(basename $line)
    ckpt_filename="${ckpt_filename%.*}"
    printf "ckpt_filename: $ckpt_filename\n"
    # Take the hdf5 file with the same name as the ckpt file and move it in the folder of the ckpt file
    hdf5_file=$(find ../outputs/ -type f | grep $ckpt_filename.hdf5)
    printf "hdf5_file: $hdf5_file\n"
    # If the hdf5 file exists, move it in the folder of the ckpt file
    if [ -n "$hdf5_file" ]; then
        printf "Moving $hdf5_file to $ckpt_path\n"
        # mv $hdf5_file $ckpt_path
    fi
done

