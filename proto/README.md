Install standalone protobuf compiler:
```
sudo apt install -y protobuf-compiler
protoc --version  # Ensure compiler version is 3+
```

Python package:
```
pip install protobuf
```
[Language Guide (proto 3)](https://protobuf.dev/programming-guides/proto3/)

[Protocol Buffer Basics: Python](https://protobuf.dev/getting-started/pythontutorial/)

To compile just execute proto/make_python.sh
Or, if you want to compile only selected files, use:
```
protoc --proto_path=. --python_out=pyi_out:. common.proto
protoc --proto_path=. --python_out=pyi_out:. agent.proto
protoc --proto_path=. --python_out=pyi_out:. tgbot.proto
```
