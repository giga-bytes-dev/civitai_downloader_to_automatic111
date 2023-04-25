#  civitai_downloader_to_automatic111 with download samples and metainfo and check models hashes

You can download all models by user
You can download all loras or ALL
You can download some model

Minimal python 3.10.9 (tested on windows)

# install with venv

TODO

# install without venv

```
py -3 pip install -r requirements.txt
py -3 main.py --help
```


Example commands for add user download all models to folder with options of no download ckpt files, 
no check exist files hashes (only size), no write civitai_model.json whet it exists yet, 

```
py -3 main.py download-models-for-user-command --ignore-ckpt --disable-sec-checks --no-check-hash-for-exist --write-json-and-desc_when_not_exists_only --sd-webui-root-dir "J:\download" https://civitai.com/user/example111
```

```
py -3 main.py download-model-command --ignore-ckpt --no-check-hash-for-exist --disable-sec-checks --sd-webui-root-dir "M:\download" https://civitai.com/models/1111/example_model
```


# TODO

1) Download by file with urls

### this is tested on windows now