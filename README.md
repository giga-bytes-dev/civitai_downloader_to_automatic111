#  civitai_downloader_to_automatic111 with download samples and metainfo and check models hashes

You can download all models by user
You can download all loras or ALL
You can download some model

# TODO

1) Download by file with urls

### this is tested on windows now

Parameters:

|                      |   |
|----------------------|---|
| --disable-sec-checks | ? |
| --sd-webui-root-dir  |   |



Example commands
```
py -3 main.py download-model-command --disable-sec-checks --sd-webui-root-dir "M:\download" https://civitai.com/models/1111/example_model

py -3 main.py download-models-for-user-command --sd-webui-root-dir "J:\download" --disable-sec-checks https://civitai.com/user/example_user
```