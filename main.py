import datetime as dt
import json
import math
import os
import platform
import re
from json import dump
from os import path
from os.path import abspath
from pathlib import Path
from re import Match
from typing import Optional, Dict

import click
from blake3 import blake3
from colorama import Fore, Style
from requests import get
from tqdm import tqdm

# some code from https://gist.github.com/tobiasraabe/58adee67de619ce621464c1a6511d7d9
# resume download not supported on civitai

remove_non_english_with_dots = lambda s: re.sub(r'[^a-zA-Z\d\s\n\.]', ' ', s)
remove_non_english_without_dots = lambda s: re.sub(r'[^a-zA-Z\d\s\n\.]', ' ', s)


def remove_multiple_underscores(text):
    result = []
    prev_char = None
    for char in text:
        if char == "_" and prev_char == "_":
            continue
        result.append(char)
        prev_char = char
    return "".join(result)


def process_str_string(input: str, with_dots: bool) -> str:
    if with_dots:
        first_step = remove_non_english_with_dots(input).rstrip().lstrip().replace(" ", "_")
    else:
        first_step = remove_non_english_without_dots(input).rstrip().lstrip().replace(" ", "_")
    return remove_multiple_underscores(first_step)


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


def download_file(url: str, file_save_path_str_path: str,
                  remove_incompleted_files: bool,
                  file_size_kb_from_civitai: Optional[float] = None,  # 6207.875
                  blake3_hash_from_civitai: Optional[str] = None) -> None:
    file_save_path = Path(file_save_path_str_path)

    if file_save_path.is_file() and file_size_kb_from_civitai is not None:
        file_size_offline = file_save_path.stat().st_size
        file_size_offline_converted_to_civitai = float(file_size_offline / 1024)

        print(f"file_size_online = {file_size_kb_from_civitai}")
        print(f"file_size_offline bytes = {file_size_offline}")
        print(f"file_size_offline_in_float_civitai = {file_size_offline_converted_to_civitai}")

        if not math.isclose(file_size_kb_from_civitai, file_size_offline_converted_to_civitai):
            if blake3_hash_from_civitai is not None \
                    and check_blake3_hash_and_print(file_save_path_str_path, blake3_hash_from_civitai):
                print(Fore.GREEN + f'File {url} to {file_save_path_str_path} is downloaded yet.'
                                   f' size from civitai != offline, but hashes are equals (bug in code)?')
                print(Style.RESET_ALL)
                return

            print(Fore.YELLOW + f'File {url} to {file_save_path_str_path} is incomplete. '
                                f'Start download with rename incomplete file.')
            print(Style.RESET_ALL)

            inc_file_save_str_path = path.join(file_save_path.parent, file_save_path.name + ".inc")

            if Path(inc_file_save_str_path).is_file():
                print(Fore.YELLOW + f'Detected yet exists old incompleted file. Remove')
                if remove_incompleted_files:
                    os.remove(inc_file_save_str_path)
                else:
                    print(Fore.YELLOW + f'Cannot remove incompleted_file.exit!')
                    exit(1)

            print(Fore.YELLOW + f'Rename {file_save_path_str_path} to {inc_file_save_str_path}')
            Path(file_save_path_str_path).rename(inc_file_save_str_path)
            print(Fore.GREEN + f'Rename ok')
            print(Style.RESET_ALL)

            if remove_incompleted_files:
                os.remove(inc_file_save_str_path)

            simple_download(url, str(file_save_path))
            if blake3_hash_from_civitai is not None:
                if check_blake3_hash_and_print(file_save_path_str_path, blake3_hash_from_civitai):
                    print(Fore.GREEN + 'downloaded hashes checked. All ok.')
                    print(Style.RESET_ALL)
                    return
                else:
                    print(Fore.RED + 'downloaded hashes check fail. bad!!!')
                    print(Style.RESET_ALL)
                    return
                    # TODO remove file??? or create invalid file mark (filename + .invalid)?
        else:
            print(f'File {url} to {file_save_path_str_path} is complete. Skip download.')
            check_yet_exists_file = True
            if blake3_hash_from_civitai is not None and check_yet_exists_file:
                if check_blake3_hash_and_print(file_save_path_str_path, blake3_hash_from_civitai):
                    print(Fore.GREEN + 'check exists file hash checked ok.')
                    print(Style.RESET_ALL)
                    return
                else:
                    print(Fore.GREEN + 'check exists file hash checked fail. bad!')
                    print(Style.RESET_ALL)
                    # TODO remove file??? or create invalid file mark (falename + .invalid)?
                    return
    else:
        print(f'File {url} to {file_save_path_str_path} does not exist. Start download.')
        simple_download(url, str(file_save_path))
        if blake3_hash_from_civitai is not None:
            if check_blake3_hash_and_print(file_save_path_str_path, blake3_hash_from_civitai):
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
            desc=Path(fname).name,
            total=total,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
    ) as bar:
        for data in resp.iter_content(chunk_size=chunk_size):
            size = file.write(data)
            bar.update(size)


CIVITAI_MODEL_REGEX_PATTERN = re.compile(r"^((http|https)://)civitai[.]com/models/(?P<model_id>\d+)")


# types of civitai resources
# 'Checkpoint' -> 'models\Stable-diffusion'
# LORA -> 'models\LoRA'
# Poses -> models\Poses
# -> extensions\sd-webui-additional-networks\models\lora\Locon
def get_web_ui_folder_by_type(base_path: str, type_str: str) -> str:
    if type_str == "Checkpoint":
        return path.join(base_path, "models", "Stable-diffusion")
    elif type_str == "LORA":
        return path.join(base_path, "models", "LoRA")
    elif type_str == "Poses":
        return path.join(base_path, "models", "Poses")
    elif type_str == "LoCon":
        return path.join(base_path, "extensions", "sd-webui-additional-networks", "models", "lora", "Locon")
    elif type_str == "TextualInversion":
        return path.join(base_path, "embeddings")
    else:
        raise Exception("Not supported type yet?")


def find_exist_image_name_by_hash(all_names_and_hashes_dict: Dict[str, str], hash: str) -> Optional[str]:
    for search_file_name, search_file_hash in all_names_and_hashes_dict.items():
        if search_file_hash == hash:
            print(f"Skip download exists image what located at name {search_file_name}")
            return search_file_name
    return None


@click.group()
def cli():
    pass


CIVITAI_USER_REGEX_PATTERN = re.compile(r"^((http|https)://)civitai[.]com/user/(?P<user_name>\w+)$")


@cli.command()
@click.option('--sd-webui-root-dir', type=str, required=True)
@click.option('--no-download', is_flag=True)
@click.option('--disable-sec-checks', is_flag=True)
@click.option('--remove-incompleted-files', is_flag=True)
@click.argument('url', type=str, required=True)
def download_models_for_user_command(sd_webui_root_dir: str,
                             no_download: bool,
                             disable_sec_checks: bool,
                             remove_incompleted_files: bool,
                             url: str):
    download_models_for_user(sd_webui_root_dir=sd_webui_root_dir,
                             no_download=no_download,
                             disable_sec_checks=disable_sec_checks,
                             remove_incompleted_files=remove_incompleted_files,
                             url=url)
def download_models_for_user(sd_webui_root_dir,
                             no_download: bool,
                             disable_sec_checks: bool,
                             remove_incompleted_files: bool,
                             url: str):
    civitai_url_match: Optional[Match] = re.fullmatch(CIVITAI_USER_REGEX_PATTERN, url)
    click.echo(f"url = {url}")
    if civitai_url_match is None:
        print("not valid civitai user page url.exit!")
        exit(1)

    user_name_str = civitai_url_match.group("user_name")
    print(f"user_name_str = {user_name_str}")

    next_page: Optional[str] = f"https://civitai.com/api/v1/models?username={user_name_str}"
    while next_page is not None:
        r = get(next_page)
        if r.status_code != 200:
            print("Get model info by civitai error! exit!")
            exit(1)

        for item in r.json()["items"]:
            url_for_download = f"https://civitai.com/models/{item['id']}"
            download_model(sd_webui_root_dir=sd_webui_root_dir,
                                   no_download=no_download,
                                   disable_sec_checks=disable_sec_checks,
                                   remove_incompleted_files=remove_incompleted_files,
                                   url=url_for_download)


@cli.command()
@click.option('--sd-webui-root-dir', type=str, required=True)
@click.option('--no-download', is_flag=True)
@click.option('--disable-sec-checks', is_flag=True)
@click.option('--remove-incompleted-files', is_flag=True)
@click.argument('url', type=str, required=True)
def download_model_command(sd_webui_root_dir,
                           no_download: bool,
                           disable_sec_checks: bool,
                           remove_incompleted_files: bool,
                           url: str):
    download_model(sd_webui_root_dir=sd_webui_root_dir,
                   no_download=no_download,
                   disable_sec_checks=disable_sec_checks,
                   remove_incompleted_files=remove_incompleted_files,
                   url=url)


def download_model(sd_webui_root_dir,
                           no_download: bool,
                           disable_sec_checks: bool,
                           remove_incompleted_files: bool,
                           url: str):
    click.echo("Options:")
    click.echo(f"--sd-webui-root-dir = {sd_webui_root_dir}")
    click.echo(f"--no-download = {no_download}")
    click.echo(f"--disable-sec-checks = {disable_sec_checks}")
    click.echo(f"--remove-incompleted-files = {remove_incompleted_files}")
    click.echo(f"url = {url}\n")

    sd_webui_root_dir = abspath(sd_webui_root_dir)
    print(f"sd_webui_root_dir = {sd_webui_root_dir}")

    print(f"args.url = {url}")

    civitai_url_match: Optional[Match] = re.match(CIVITAI_MODEL_REGEX_PATTERN, url)
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
    # print(f"model_page_name_procesed = {model_page_name_procesed}")

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
    for index, model_version_json_data in enumerate(model_versions_items):  # print(index, item)
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
            # print(f"\t\ttype: {current_file['type']}")
            # "pickleScanResult": "Success",
            # "pickleScanMessage": "No Pickle imports",
            # "virusScanResult": "Success",

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

            try:
                file_hash_blake3 = current_file['hashes']['BLAKE3']
            except KeyError:
                print(Fore.RED + '\tNo hash in json from cilivai. Hash no calculated on servers of cilivai yet?')
                print(Fore.RED + '\tHash check disabled now')
                print(Style.RESET_ALL)

            if file_model_is_safe or disable_sec_checks:
                if no_download:
                    print(f"simulate download(url={current_file['downloadUrl']}, "
                          f"download_model_data_entry_path={download_model_data_entry_path})")
                else:

                    download_file(url=current_file['downloadUrl'],
                                  file_save_path_str_path=download_model_data_entry_path,
                                  remove_incompleted_files=remove_incompleted_files,
                                  file_size_kb_from_civitai=current_file['sizeKB'],
                                  blake3_hash_from_civitai=file_hash_blake3)
            else:
                print(Fore.RED + 'I will not download this!!Unsafe')
                print(Style.RESET_ALL)
                print("I will not download this!!Unsafe. You can disable it with --disable-sec-checks true")

            all_names_and_hashes = dict()
            max_index_int_name = 0

            for current_file in os.listdir(path=path_for_model_samples_folder):
                if not current_file.endswith('.json'):
                    continue
                path_to_current_json = path.join(path_for_model_samples_folder, current_file)

                current_file_name_without_ext = Path(current_file).stem
                if current_file_name_without_ext.isdigit():
                    current_num = int(current_file_name_without_ext)
                    if current_num > max_index_int_name:
                        max_index_int_name = current_num

                with open(path_to_current_json, 'r') as fi:
                    dict_current_json = json.load(fi)
                    all_names_and_hashes[current_file_name_without_ext] = dict_current_json["hash"]

            print(f"max_index_int_name = {max_index_int_name}")

            for index, image_json in enumerate(model_version_json_data["images"]):

                image_name_by_hash = find_exist_image_name_by_hash(all_names_and_hashes_dict=all_names_and_hashes,
                                                                   hash=image_json["hash"])

                # json with hash was founded
                if image_name_by_hash is not None:
                    if not Path(path.join(path_for_model_samples_folder, image_name_by_hash + ".jpg")).is_file():
                        print(Fore.RED + '\tJson file exists but jpg file no found!!')
                        print(Style.RESET_ALL)
                    continue

                max_index_int_name += 1
                sample_json_data_name = str(max_index_int_name) + ".json"
                path_for_save_image = path.join(path_for_model_samples_folder, str(max_index_int_name) + ".jpg")
                path_for_json = path.join(path_for_model_samples_folder, sample_json_data_name)
                path_for_json_meta = path.join(path_for_model_samples_folder, str(max_index_int_name) + ".meta")
                if no_download:
                    print(f"simulate download(url={image_json['url']}, path_for_save_image={path_for_save_image}))")
                else:
                    simple_download(image_json['url'], path_for_save_image)

                with open(path_for_json, 'w') as f:
                    dump(image_json, f)
                    print(f"save {sample_json_data_name} ok")

                with open(path_for_json_meta, 'w') as f:
                    dump(image_json['meta'], f)


if __name__ == '__main__':
    cli()
