import json

from mypylib.mypylib import color_print
from mytoncore import local as mytoncore_local, hex2base64
from mytonctrl import ton


def parse_config(name: str, config: dict, vset: list = None):
    """
    Converts config to validator-console friendly format
    :param name: custom overlay name
    :param config: config
    :param vset: list of validators adnl addresses, can be None if `@validators` not in config
    :return:
    """
    result = {
        "name": name,
        "nodes": []
    }
    for k, v in config.items():
        if k == '@validators' and v:
            if vset is None:
                raise Exception("Validators set is not defined but @validators is in config")
            for v_adnl in vset:
                result["nodes"].append({
                    "adnl_id": hex2base64(v_adnl),
                    "msg_sender": False,
                })
        else:
            result["nodes"].append({
                "adnl_id": hex2base64(k),
                "msg_sender": v["msg_sender"],
            })
            if v["msg_sender"]:
                result["nodes"][-1]["msg_sender_priority"] = v["msg_sender_priority"]
    return result


def add_custom_overlay(args):
    if len(args) != 2:
        color_print("{red}Bad args. Usage:{endc} add_custom_overlay <name> <path_to_config>")
        return
    path = args[1]
    with open(path, 'r') as f:
        config = json.load(f)
    mytoncore_local.db['custom_overlays'][args[0]] = config


def list_custom_overlays(args):
    for k, v in mytoncore_local.db['custom_overlays'].items():
        color_print(f"Custom overlay {{bold}}{k}{{endc}}:")
        print(json.dumps(v, indent=4))


def delete_custom_overlay(args):
    if len(args) != 1:
        color_print("{red}Bad args. Usage:{endc} delete_custom_overlay <name>")
        return
    del mytoncore_local.db['custom_overlays'][args[0]]


def delete_custom_overlay_from_vc(name: str):
    result = ton.validatorConsole.Run(f"delcustomoverlay {name}")
    return 'success' in result


def add_custom_overlay_to_vc(config: dict):
    mytoncore_local.add_log(f"Adding custom overlay {config['name']}", "debug")
    path = ton.tempDir + f'/custom_overlay_{config["name"]}.json'
    with open(path, 'w') as f:
        json.dump(config, f)
    result = ton.validatorConsole.Run(f"addcustomoverlay {path}")
    return 'success' in result


def deploy_custom_overlays():
    result = ton.validatorConsole.Run("showcustomoverlays")
    if 'unknown command' in result:
        return  # node old version
    names = []
    for line in result.split('\n'):
        if line.startswith('Overlay'):
            names.append(line.split(' ')[1].replace('"', ''))

    config34 = ton.GetConfig34()
    current_el_id = config34['startWorkTime']
    current_vset = [i["adnlAddr"] for i in config34['validators']]

    config36 = ton.GetConfig36()
    next_el_id = config36['startWorkTime'] if config36['validators'] else 0
    next_vset = [i["adnlAddr"] for i in config36['validators']]

    for name in names:
        # check that overlay still exists in mtc db
        pure_name = name
        suffix = name.split('_')[-1]
        if suffix.startswith('elid') and suffix.split('elid')[-1].isdigit():  # probably election id
            pure_name = '_'.join(name.split('_')[:-1])
            el_id = int(suffix.split('elid')[-1].isdigit())
            if el_id not in (current_el_id, next_el_id):
                mytoncore_local.add_log(f"Overlay {name} is not in current or next election, deleting", "debug")
                delete_custom_overlay_from_vc(name)  # delete overlay if election id is not in current or next election
                continue

        if pure_name not in mytoncore_local.db['custom_overlays']:
            mytoncore_local.add_log(f"Overlay {name} is not in mtc db, deleting", "debug")
            delete_custom_overlay_from_vc(name)  # delete overlay if it's not in mtc db

    for name, config in mytoncore_local.db['custom_overlays'].items():
        if name in names:
            continue
        if '@validators' in config:
            new_name = name + '_elid' + str(current_el_id)
            if new_name not in names:
                node_config = parse_config(new_name, config, current_vset)
                add_custom_overlay_to_vc(node_config)

            if next_el_id != 0:
                new_name = name + '_elid' + str(next_el_id)
                if new_name not in names:
                    node_config = parse_config(new_name, config, next_vset)
                    add_custom_overlay_to_vc(node_config)
        else:

            node_config = parse_config(name, config)
            add_custom_overlay_to_vc(node_config)
