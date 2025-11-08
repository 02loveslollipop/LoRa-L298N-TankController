#!/bin/bash

#check if current system is aarch64
if [ "$(uname -m)" != "aarch64" ]; then
    # add flags for go build cross compile
    export GOARCH=arm64
    export GOOS=linux
fi

go build -o streamer main.go -trimpath 

if [ $? -ne 0 ]; then
    echo "Build failed"
    exit 1
fi

echo "Build succeeded"
echo "You can run the streamer using ./run.sh"
exit 0