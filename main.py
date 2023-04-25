import datetime as dt
import json
import math
import os
import platform
import re
from json import dump, JSONDecodeError
from os import path
from os.path import abspath
from pathlib import Path
from re import Match
from typing import Optional, Dict, Any, List
from datetime import datetime

import click
import cloudscraper as cloudscraper
import requests
from blake3 import blake3
from bs4 import BeautifulSoup
from colorama import Fore, Style
from requests import get
from tqdm import tqdm

sess = requests.Session()

sess.headers = {
    'referer': 'imagecache.civitai.com',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    },
    sess=sess
)

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
                  no_check_hash_for_exist: bool,
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
            if blake3_hash_from_civitai is not None and not no_check_hash_for_exist:
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


def simple_download(url: str, fname: str, chunk_size=4096, use_cloudscraper: bool = False):
    if use_cloudscraper:
        resp = scraper.get(url, stream=True)
    else:
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

class CivitaiDownloadModelError(Exception):
    pass


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
    elif type_str == "Hypernetwork":
        return path.join(base_path, "models", "hypernetworks")
    elif type_str == "Other":
        return path.join(base_path, "models", "Other")
    elif type_str == "Wildcards":
        return path.join(base_path, "Wildcards")
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

REGEX_CIVITAI_IMAGE_FROM_CACHE_PATTERN = re.compile(r"^((https)://)imagecache[.]civitai[.]com/(?P<unc1>\w+)/(?P<uuid_image1>\w+-\w+-\w+-\w+-\w+)/width=(?P<image_width>\d+)/(?P<uuid_image2>\w+-\w+-\w+-\w+-\w+)$")

@cli.command()
@click.option('--sd-webui-root-dir', type=str, required=True)
@click.option('--no-download', is_flag=True)
@click.option('--disable-sec-checks', is_flag=True)
@click.option('--remove-incompleted-files', is_flag=True)
@click.option('--ignore-ckpt', is_flag=True, default=False)
@click.option('--no-check-hash-for-exist', is_flag=True)
@click.option('--model-type-filter', type=click.Choice(['NONE', 'LORA', 'Model'], case_sensitive=False), default="NONE")
@click.option('--download-pics-from-desc/--no-download-pics-from_desc', default=True)
@click.option('--write-json-and-desc_when_not_exists_only/--no-write-json-and-desc-when-not-exists-only', default=False)
@click.argument('url', type=str, required=True)
def download_models_for_user_command(sd_webui_root_dir: str,
                                     no_download: bool,
                                     disable_sec_checks: bool,
                                     remove_incompleted_files: bool,
                                     model_type_filter: str,
                                     url: str,
                                     no_check_hash_for_exist: bool,
                                     download_pics_from_desc: bool,
                                     ignore_ckpt: bool,
                                     write_json_and_desc_when_not_exists_only: bool):
    download_models_for_user(sd_webui_root_dir=sd_webui_root_dir,
                             no_download=no_download,
                             disable_sec_checks=disable_sec_checks,
                             remove_incompleted_files=remove_incompleted_files,
                             model_type_filter=model_type_filter,
                             no_check_hash_for_exist=no_check_hash_for_exist,
                             url=url,
                             download_pics_from_desc=download_pics_from_desc,
                             write_json_and_desc_when_not_exists_only=write_json_and_desc_when_not_exists_only,
                             ignore_ckpt=ignore_ckpt)
def download_models_for_user(sd_webui_root_dir,
                             no_download: bool,
                             disable_sec_checks: bool,
                             remove_incompleted_files: bool,
                             model_type_filter: str,
                             no_check_hash_for_exist: bool,
                             url: str,
                             download_pics_from_desc: bool,
                             write_json_and_desc_when_not_exists_only: bool,
                             ignore_ckpt: bool):
    civitai_url_match: Optional[Match] = re.fullmatch(CIVITAI_USER_REGEX_PATTERN, url)
    click.echo(f"url = {url}")
    skip_download_file_ext_list = []
    if ignore_ckpt:
        skip_download_file_ext_list.append("ckpt")
    if civitai_url_match is None:
        print("not valid civitai user page url.exit!")
        exit(1)


    user_name_str = civitai_url_match.group("user_name")
    print(f"user_name_str = {user_name_str}")

    next_page: Optional[str] = f"https://civitai.com/api/v1/models?username={user_name_str}"
    while next_page is not None:
        r = get(next_page)
        if r.status_code != 200:
            message_error = "Get model info by civitai error!"
            raise CivitaiDownloadModelError(message_error)
        data = r.json()
        for item in data["items"]:
            url_for_download = f"https://civitai.com/models/{item['id']}"
            click.echo(f"begin {url_for_download}")
            if model_type_filter.upper() != "NONE":
                click.echo(f"model_type_filter = {model_type_filter}")
                if item["type"] != model_type_filter:
                    click.echo(f"skip model. filter enabled to download {model_type_filter} only")
                    continue
            try:
                download_model(sd_webui_root_dir=sd_webui_root_dir,
                               no_download=no_download,
                               disable_sec_checks=disable_sec_checks,
                               remove_incompleted_files=remove_incompleted_files,
                               no_check_hash_for_exist=no_check_hash_for_exist,
                               url=url_for_download,
                               download_pics_from_desc=download_pics_from_desc,
                               write_json_and_desc_when_not_exists_only=write_json_and_desc_when_not_exists_only,
                               skip_download_file_ext_list=skip_download_file_ext_list)
            except CivitaiDownloadModelError as e:
                click.echo(e)

        if "nextPage" in data["metadata"]:
            next_page = data["metadata"]["nextPage"]
            click.echo(f"next page = {next_page}")
        else:
            next_page = None


@cli.command()
@click.option('--sd-webui-root-dir', type=str, required=True)
@click.option('--no-download', is_flag=True)
@click.option('--disable-sec-checks', is_flag=True)
@click.option('--no-check-hash-for-exist', is_flag=True)
@click.option('--remove-incompleted-files', is_flag=True)
@click.option('--ignore-ckpt', is_flag=True, default=False)
@click.option('--download-pics-from-desc/--no-download-pics-from_desc', default=True)
@click.option('--write-json-and-desc_when_not_exists_only/--no-write-json-and-desc-when-not-exists-only', default=False)
@click.argument('url', type=str, required=True)
def download_model_command(sd_webui_root_dir,
                           no_download: bool,
                           disable_sec_checks: bool,
                           no_check_hash_for_exist: bool,
                           remove_incompleted_files: bool,
                           url: str,
                           ignore_ckpt: bool,
                           download_pics_from_desc: bool,
                           write_json_and_desc_when_not_exists_only: bool):
    skip_download_file_ext_list = []
    if ignore_ckpt:
        skip_download_file_ext_list.append("ckpt")

    download_model(sd_webui_root_dir=sd_webui_root_dir,
                   no_download=no_download,
                   disable_sec_checks=disable_sec_checks,
                   no_check_hash_for_exist=no_check_hash_for_exist,
                   remove_incompleted_files=remove_incompleted_files,
                   url=url,
                   download_pics_from_desc=download_pics_from_desc,
                   write_json_and_desc_when_not_exists_only=write_json_and_desc_when_not_exists_only,
                   skip_download_file_ext_list=skip_download_file_ext_list)


def download_pics(model_data_json: Any, path_for_pics_folder) -> str:
    description_html = model_data_json['description']
    if description_html is None:
        return ""
    soup = BeautifulSoup(description_html, 'html.parser')
    for img_tag in soup.find_all('img'):
        img_url = img_tag['src']
        civitai_image_match: Optional[Match] = re.fullmatch(REGEX_CIVITAI_IMAGE_FROM_CACHE_PATTERN, img_url)
        if civitai_image_match is None:
            click.echo("Invalid cache url. go to next img")
            continue

        uuid_image_name = civitai_image_match.group("uuid_image2")
        image_width = civitai_image_match.group("image_width")
        path_for_pic_in_pics_folder = path.join(path_for_pics_folder, uuid_image_name)
        img_url_with_width_zero = img_url.replace("width=" + image_width, 'width=0')
        if Path(path_for_pic_in_pics_folder).is_file():
            click.echo(f"File {uuid_image_name} exists yet")
        else:
            simple_download(img_url_with_width_zero, str(path_for_pic_in_pics_folder), use_cloudscraper=True)
        img_tag['src'] = "pics/" + uuid_image_name
    return str(soup)

def file_rename_to_name_with_past_mask(file_path: str, dest_begin_file_name: str) -> Optional[str]:
    file_path_Path = Path(file_path)
    current_date_time = datetime.now().strftime("%d_%m_%Y__%H_%M_%S")

    new_name_of_destination_file = dt.datetime.fromtimestamp(creation_date(file_path)).strftime(
        dest_begin_file_name + "_%d_%m_%Y__%H_%M__%S_now_" + current_date_time) + ".json"
    destination_file_path = path.join(file_path_Path.parent, new_name_of_destination_file)
    try:
        file_path_Path.rename(destination_file_path)
        click.echo(f"Rename current {file_path} to {destination_file_path} ok")
        return destination_file_path
    except FileNotFoundError:
        click.echo(f"Rename current {file_path} to {destination_file_path} fail")
    return None

def download_or_update_json_model_info_with_pics(folder_for_current_model: str,
                                                 model_data_json: Any,
                                                 download_pics_from_desc: bool,
                                                 write_json_and_desc_when_not_exists_only: bool) -> None:
    CIVITAI_MODEL_ORIGINAL_NAME_JSON = "civitai_model.original.json"
    CIVITAI_MODEL_DESC_NAME_HTML = "civitai_model_desc.html"

    path_for_pics_folder = path.join(folder_for_current_model, "pics")
    Path(path_for_pics_folder).mkdir(parents=True, exist_ok=True)

    path_for_model_original_json = path.join(folder_for_current_model, CIVITAI_MODEL_ORIGINAL_NAME_JSON)
    path_for_model_desc_json = path.join(folder_for_current_model, CIVITAI_MODEL_DESC_NAME_HTML)
    print(f"path_for_model_original_json = {path_for_model_original_json}")

    if write_json_and_desc_when_not_exists_only:
        if Path(path_for_model_original_json).is_file():
            click.echo(f"Enabled write_json_and_desc_when_not_exists_only option. Detected exists {CIVITAI_MODEL_ORIGINAL_NAME_JSON} file. skip desc and pics rename and download")
            return

    # TODO check, we need rename current exists json and write current?
    # if no, then write_model_and_original_data = False
    if True:
        if Path(path_for_model_desc_json).is_file():
            file_rename_to_name_with_past_mask(path_for_model_desc_json, "civitai_model_desc")
        if Path(path_for_model_original_json).is_file():
            file_rename_to_name_with_past_mask(path_for_model_original_json, "civitai_model_orig")

    with open(path_for_model_original_json, 'w') as f:
        dump(model_data_json, f)
    if download_pics_from_desc:
        model_data_json_with_fixed_paths = download_pics(model_data_json, path_for_pics_folder)
        with open(path_for_model_desc_json, 'w') as f:
            dump(model_data_json_with_fixed_paths, f)


# realisticVisionV20_v20.ckpt
def skip_file_name_ext_by_skip_list(skip_download_file_exts: List[str], file_name_with_ext: str) -> bool:
    for skip_download_file_ext in skip_download_file_exts:
        if file_name_with_ext.endswith(f".{skip_download_file_ext}"):
            return True
    return False


def download_model(sd_webui_root_dir,
                           no_download: bool,
                           disable_sec_checks: bool,
                           remove_incompleted_files: bool,
                           no_check_hash_for_exist: bool,
                           url: str,
                           download_pics_from_desc: bool,
                           write_json_and_desc_when_not_exists_only: bool,
                           skip_download_file_ext_list: List[str]):
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
        message_error = "Get model info by civitai error!"
        print(message_error)
        raise CivitaiDownloadModelError(message_error)

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

    download_or_update_json_model_info_with_pics(folder_for_current_model=folder_for_current_model,
                                                 model_data_json=model_data_json,
                                                 download_pics_from_desc=download_pics_from_desc,
                                                 write_json_and_desc_when_not_exists_only=write_json_and_desc_when_not_exists_only)


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

            # skip_download_file_ext
            if file_model_is_safe or disable_sec_checks:
                if no_download:
                    print(f"simulate download(url={current_file['downloadUrl']}, "
                          f"download_model_data_entry_path={download_model_data_entry_path})")
                elif skip_file_name_ext_by_skip_list(skip_download_file_ext_list, current_file['name']):
                    print(f"skip download by skip_list")
                else:
                    download_file(url=current_file['downloadUrl'],
                                  no_check_hash_for_exist=no_check_hash_for_exist,
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
                    try:
                        dict_current_json = json.load(fi)
                    except JSONDecodeError as e:
                        print(f"decode json error. {e} json file by path {path_to_current_json}")
                        raise e
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
