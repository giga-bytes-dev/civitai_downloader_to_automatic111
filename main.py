import argparse
import math
import os
import platform
import re
from json import dump
from os import path
from os.path import abspath
from pathlib import Path
from re import Match
from typing import Optional
import datetime as dt

from blake3 import blake3
from colorama import Fore, Style
from requests import get
from tqdm import tqdm

# some code from https://gist.github.com/tobiasraabe/58adee67de619ce621464c1a6511d7d9
# resume download not supported on civitai

remove_non_english_with_dots = lambda s: re.sub(r'[^a-zA-Z\d\s\n\.]', ' ', s)
remove_non_english_without_dots = lambda s: re.sub(r'[^a-zA-Z\d\s\n\.]', ' ', s)

def process_str_string(input: str, with_dots: bool) -> str:
    if with_dots:
        return remove_non_english_with_dots(input).rstrip().lstrip().replace(" ", "_")
    return remove_non_english_without_dots(input).rstrip().lstrip().replace(" ", "_")

def creation_date(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        return os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            return stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return stat.st_mtime


def toFixed(numObj, digits=0):
    return f"{numObj:.{digits}f}"

def compute_blake3(file_path: str) -> str:
    hash_blake3 = blake3()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_blake3.update(chunk)
    return hash_blake3.hexdigest().upper()

def check_blake3_hash_and_print(file_path: str, blake3_hash_from_civitai: str) -> bool:
    blake3_hash_str = compute_blake3(str(file_path))
    print(f"blake3 hash: {blake3_hash_str}")
    if blake3_hash_from_civitai == blake3_hash_str:
        print(f"For file hash check ok")
        return True

    print(Fore.RED + 'For file hash check fail')
    print(Style.RESET_ALL)
    return False


def download_file(url: str, file_save_path: str,
                  file_size_kb_from_civitai: Optional[float] = None, # 6207.875
                  blake3_hash_from_civitai: Optional[str] = None) -> None:
    # r = head(url)
    # file_size_online = int(r.headers.get('content-length', 0))

    file_save = Path(file_save_path)

    if file_save.is_file() and file_size_kb_from_civitai is not None:
        file_size_offline = file_save.stat().st_size
        file_size_offline_converted_to_civitai = float(file_size_offline/1024)

        print(f"file_size_online = {file_size_kb_from_civitai}")
        print(f"file_size_offline bytes = {file_size_offline}")
        print(f"file_size_offline_in_float_civitai = {file_size_offline_converted_to_civitai}")

        if not math.isclose(file_size_kb_from_civitai, file_size_offline_converted_to_civitai):
            if blake3_hash_from_civitai is not None \
                    and check_blake3_hash_and_print(file_save_path, blake3_hash_from_civitai):
                print(Fore.GREEN + f'File {url} to {file_save_path} is downloaded yet.'
                                   f' size from civitai != offline, but hashes are equals (bug in code)?')
                print(Style.RESET_ALL)
                return

            print(Fore.YELLOW + f'File {url} to {file_save_path} is incomplete. Start download with rewrite.')
            print(Style.RESET_ALL)
            # TODO rename incompleted file to .incompleted
            simple_download(url, str(file_save), file_size_offline)
            if blake3_hash_from_civitai is not None:
                if check_blake3_hash_and_print(file_save_path, blake3_hash_from_civitai):
                    print(Fore.GREEN + 'downloaded hashes checked. All ok.')
                    print(Style.RESET_ALL)
                    return
                else:
                    print(Fore.RED + 'downloaded hashes check fail. bad!!!')
                    print(Style.RESET_ALL)
                    return
                    # TODO remove file??? or create invalid file mark (filename + .invalid)?
        else:
            print(f'File {url} to {file_save_path} is complete. Skip download.')
            check_yet_exists_file = True
            if blake3_hash_from_civitai is not None and check_yet_exists_file:
                if check_blake3_hash_and_print(file_save_path, blake3_hash_from_civitai):
                    print(Fore.GREEN + 'check exists file hash checked ok.')
                    print(Style.RESET_ALL)
                    return
                else:
                    print(Fore.GREEN + 'check exists file hash checked fail. bad!')
                    print(Style.RESET_ALL)
                    # TODO remove file??? or create invalid file mark (falename + .invalid)?
                    return
    else:
        print(f'File {url} to {file_save_path} does not exist. Start download.')
        simple_download(url, str(file_save))
        if blake3_hash_from_civitai is not None:
            if check_blake3_hash_and_print(file_save_path, blake3_hash_from_civitai):
                print(f"check downloaded file hash checked ok.")
                return
            else:
                print(f"check downloaded file hash checked fail. bad!")
                return
                # TODO remove file??? or create invalid file mark (falename + .invalid)?

def simple_download(url: str, fname: str, chunk_size=4096):
    resp = get(url, stream=True)
    total = int(resp.headers.get('content-length', 0))
    with open(fname, 'wb') as file, tqdm(
        desc=fname,
        total=total,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in resp.iter_content(chunk_size=chunk_size):
            size = file.write(data)
            bar.update(size)

CIVITAI_MODEL_REGEX_PATTERN = re.compile(r"^((http|https)://)civitai[.]com/models/(?P<model_id>\d+)/(.+)$")

# types of civitai resources
# 'Checkpoint' -> 'models\Stable-diffusion'
# LORA -> 'models\LoRA'
def get_web_ui_folder_by_type(base_path: str, type_str: str) -> str:
    if type_str == "Checkpoint":
        return path.join(base_path, "models", "Stable-diffusion")
    elif type_str == "LORA":
        return path.join(base_path, "models", "LoRA")
    else:
        raise Exception("Not supported type yet?")


def main():
    parser = argparse.ArgumentParser(description='Download from civitai')
    parser.add_argument('--sd-webui-root-dir', type=str, help='stable-diffusion-webui dir', default="sd-webui-root-dir")
    parser.add_argument('--no-download', type=bool, help='no download', default=False)
    parser.add_argument('--disable-sec-checks', type=bool, help='no download', default=False)
    parser.add_argument('url', type=str)
    args = parser.parse_args()

    sd_webui_root_dir = abspath(args.sd_webui_root_dir)
    print(f"sd_webui_root_dir = {sd_webui_root_dir}")

    print(f"args.url = {args.url}")

    civitai_url_match: Optional[Match] = re.fullmatch(CIVITAI_MODEL_REGEX_PATTERN, args.url)
    if civitai_url_match is None:
        print("not valid civitai model page url.exit!")
        exit(1)

    model_id_str = civitai_url_match.group("model_id")
    print(f"model_id_str = {model_id_str}")

    r = get(f"https://civitai.com/api/v1/models/{model_id_str}")
    if r.status_code != 200:
        print("Get model info by civitai error! exit!")
        exit(1)

    model_data_json = r.json()

    type_of_model = model_data_json["type"]
    model_page_name = model_data_json['name']
    model_page_name_procesed = process_str_string(model_page_name, with_dots=False)
    #print(f"model_page_name_procesed = {model_page_name_procesed}")

    print(f"@ model_page_name = {model_page_name}")
    print(f"@ model_page_name_procesed = {model_page_name_procesed}")

    print(f"type_of_model = {type_of_model}")
    folder_for_model_type = get_web_ui_folder_by_type(sd_webui_root_dir, type_of_model)
    print(f"folder_for_model = {folder_for_model_type}")

    folder_for_current_model = path.join(folder_for_model_type,
                                         f"{model_data_json['id']}_" + model_page_name_procesed)

    Path(folder_for_current_model).mkdir(parents=True, exist_ok=True)
    print(f"Create folder {folder_for_current_model} or use exists ok")

    path_for_model_json = path.join(folder_for_current_model, "civitai_model.json")
    print(f"path_for_model_json = {path_for_model_json}")

    path_for_model_json_Path = Path(path_for_model_json)
    if path_for_model_json_Path.is_file():
        print(f"path_for_json = {path_for_model_json}")
        print(f"creation_date = {creation_date(path_for_model_json)}")
        file_time = dt.datetime.fromtimestamp(creation_date(path_for_model_json))
        print(file_time.strftime("%d_%m_%Y__%H_%M"))
        new_name_of_current_file = file_time.strftime("civitai_model_%d_%m_%Y__%H_%M") + ".json"
        new_file_full_path = path.join(path_for_model_json_Path.parent, new_name_of_current_file)
        path_for_model_json_Path.rename(new_file_full_path)
        print(f"Rename current {path_for_model_json} to {new_file_full_path}")

    with open(path_for_model_json, 'w') as f:
        dump(model_data_json, f)

    model_versions_items = model_data_json["modelVersions"]
    for index, model_version_json_data in enumerate(model_versions_items): #print(index, item)
        print(f"@model_version name raw = {model_version_json_data['name']}")
        model_version_name_processed = process_str_string(model_version_json_data['name'], with_dots=True)
        model_version_folder = path.join(folder_for_current_model, model_version_name_processed)

        Path(model_version_folder).mkdir(parents=True, exist_ok=True)
        print(f"Create folder {model_version_folder} or use exists ok")

        path_for_model_samples_folder = path.join(model_version_folder, "samples")

        Path(path_for_model_samples_folder).mkdir(parents=True, exist_ok=True)
        print(f"Create folder {path_for_model_samples_folder} or use exists ok")

        print("files:")
        for current_file in model_version_json_data["files"]:

            print(f"\tname: {current_file['name']}")
            print(f"\ttype: {current_file['type']}")
            print(f"\tsizeKB raw: {current_file['sizeKB']}")
            print(f"\tsizeKB raw type: {type(current_file['sizeKB'])}")
            # on all ok
            #print(f"\t\ttype: {current_file['type']}")
            #"pickleScanResult": "Success",
            #"pickleScanMessage": "No Pickle imports",
            #"virusScanResult": "Success",

            # after upload one second ago.  No hash and no scan
            # "pickleScanResult": "Pending",
            # "pickleScanMessage": null,
            # "virusScanResult": "Pending",

            print(f"\tdownload_url: {current_file['downloadUrl']}")
            download_model_data_entry_path = path.join(model_version_folder, current_file['name'])

            file_model_is_safe = False
            if current_file['pickleScanResult'] == "Success" and current_file['virusScanResult'] == "Success":
                file_model_is_safe = True
            file_hash_blake3 = None

            if "hashes" in current_file and "BLAKE3" in current_file['hashes']['BLAKE3']:
                file_hash_blake3 = current_file['hashes']['BLAKE3']
            else:
                print(Fore.RED + '\tNo hash in json from cilivai. Hash no calculated yet?')
                print(Fore.RED + '\tHash check disabled now')
                print(Style.RESET_ALL)

            if file_model_is_safe or args.disable_sec_checks:
                if args.no_download:
                    print(f"simulate download(url={current_file['downloadUrl']}, "
                          f"download_model_data_entry_path={download_model_data_entry_path})")
                else:

                    download_file(url=current_file['downloadUrl'],
                                  file_save_path=download_model_data_entry_path,
                                  file_size_kb_from_civitai=current_file['sizeKB'],
                                  blake3_hash_from_civitai=file_hash_blake3)
            else:
                print(Fore.RED + 'I will not download this!!Unsafe')
                print(Style.RESET_ALL)
                print("I will not download this!!Unsafe. You can disable it with --disable-sec-checks true")

            for index, image_json in enumerate(model_version_json_data["images"]):
                sample_json_data_name = str(index) + ".json"
                path_for_save_image = path.join(path_for_model_samples_folder, str(index) + ".jpg")
                path_for_json = path.join(path_for_model_samples_folder, sample_json_data_name)
                path_for_json_meta = path.join(path_for_model_samples_folder, str(index) + ".meta")
                if args.no_download:
                    print(f"simulate download(url={image_json['url']}, path_for_save_image={path_for_save_image}))")
                else:
                    simple_download(image_json['url'], path_for_save_image)

                with open(path_for_json, 'w') as f:
                    dump(image_json, f)
                    print(f"save {sample_json_data_name} ok")

                with open(path_for_json_meta, 'w') as f:
                    dump(image_json['meta'], f)


if __name__ == '__main__':
    main()
