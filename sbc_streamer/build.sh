#!/bin/bash

#check if current system is aarch64
if [ "$(uname -m)" != "aarch64" ]; then
    # add flags for go build cross compile
    export GOARCH=arm64
    export GOOS=linux
fi

# run with flags to minimize binary size
CGO_ENABLED=0 go build -ldflags="-s -w" -o streamer main

if [ $? -ne 0 ]; then
    echo "Build failed"
    exit 1
fi

echo "Build succeeded"
echo "You can run the streamer using ./run.sh"
exit 0