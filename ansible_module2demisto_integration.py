import yaml
from ansible.plugins.loader import fragment_loader
from ansible.utils import plugin_docs
import os
import re
from stringcase import spinalcase
from pathlib import Path
import base64

# Constants
# The Ansible dir is in the same folder as this script
BASE_PATH = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
MODULE_DIR = os.path.join(BASE_PATH, 'ansible/lib/ansible/modules/')  # Modules are stored in this location
DEFINITION_FILE = 'definitions.yml'  # the translation definition file
OUTPUT_DIR = os.path.join(BASE_PATH, 'content/Packs/Ansible_Powered_Integrations/Integrations/')
ANSIBLE_RUNNER_DOCKER_VERSION = '1.0.0.19017'  # The tag of demisto/ansible-runner to use
ANSIBLE_ONLINE_DOCS_URL = 'https://docs.ansible.com/ansible/2.9/modules/'  # The URL of the online module documentation



def find_module_file(module_name, modules_parent_path):
    for root, dir_names, file_names in os.walk(modules_parent_path):
        for file_name in file_names:
            module, extension = os.path.splitext(file_name)

            if module == '__init__' or extension != '.py':
                continue

            if module.startswith('_'):
                module = module[1:]

            if module_name == module:
                return os.path.join(root, file_name)


# load integration definition from file
with open(DEFINITION_FILE) as f:
    integrations_def = yaml.load(f, Loader=yaml.Loader)
    
    for integration_def in integrations_def:
        integration = {}

        # integration settings
        integration['display'] = integration_def.get('name')
        if len(integration_def.get('name').split()) == 1:  # If the definition `name` is single word then trust the caps
            integration['name'] = integration_def.get('name')
        else:
            integration['name'] = integration_def.get('name').replace(' ', '')
        integration['category'] = integration_def.get('category')
        integration['description'] = integration_def.get('description')
        integration['commonfields'] = {
        "id": integration['name'],
        "version": -1
        }

        integration['fromversion'] = "6.0.0"  # minimum version
        print("Creating Integration: %s" % integration['display'])


        # Integration configuration elements
        # See https://xsoar.pan.dev/docs/integrations/yaml-file#configuration for more details
        integration['configuration'] = []
        if integration_def.get('config') is not None:
            for config in integration_def.get('config'):
                integration['configuration'].append(config)

        # Add static tunables relating to host based targets
        if integration_def.get('hostbasedtarget'):
            config = {}
            config['display'] = "Concurrecy Factor"
            config['name'] = "concurrency"
            config['type'] = 0
            config['required'] = True
            config['defaultvalue'] = "4"
            config['additionalinfo'] = "If multiple hosts are specified in a command, how many hosts should be interacted with concurrently."
            integration['configuration'].append(config)
        
        commands = []
        command_examples = []
        for ansible_module in integration_def.get('ansible_modules'):
            print("Adding Module: %s" % ansible_module)

            module_path = find_module_file(ansible_module, MODULE_DIR)
            print("Found module file path: %s" % module_path)

            # doc and metadata are returned as a dict, example and returndocs are just striaght yaml
            doc, examples, returndocs, metadata = plugin_docs.get_docstring(module_path, fragment_loader)

            command = {}

            if integration_def.get('command_prefix') is not None:
                command_prefix = integration_def.get('command_prefix')
            else:
                if len(integration_def.get('name').split(' ')) == 1:  # If the definition `name` is single word then trust the caps
                    command_prefix = integration['name'].lower()
                else:
                    command_prefix = spinalcase(integration['name'])


            if not spinalcase(ansible_module).startswith(command_prefix + '-'):
                command['name'] = command_prefix + '-' + spinalcase(ansible_module)
            else:
                command['name'] = spinalcase(ansible_module)
            module_online_help = "%s%s_module.html" % (ANSIBLE_ONLINE_DOCS_URL, ansible_module)
            command['description'] = str(doc.get('short_description')) + "\n Further documentation availiable at " + module_online_help
            command['arguments'] = []

            # Arguments
            options = doc.get('options')

            # Add static arguments if integration uses host based targets
            if integration_def.get('hostbasedtarget'):
                argument = {}
                argument['name'] = "host"
                argument['description'] = "hostname or IP of target. Optionally the port can be specified using :PORT. If multiple targets are specified using an array, the integration will use the configured concurrency factor for high performance."
                argument['required'] = True
                argument['isArray'] = True
                command['arguments'].append(argument)

            if options is not None:
                for arg, option in options.items():

                    # Skip args that the definition says to ignore
                    if integration_def.get('ignored_args') is not None:
                        if arg in integration_def.get('ignored_args'):
                            continue

                    argument = {}
                    argument['name'] = str(arg)

                    if isinstance(option.get('description'),list):
                        argument['description'] = ""
                        for line_of_doco in option.get('description'):
                            if not line_of_doco.isspace():
                                clean_line_of_doco = line_of_doco.strip()  # remove begin/end whitespace
                                # remove ansible link markup 
                                # https://docs.ansible.com/ansible/latest/dev_guide/developing_modules_documenting.html#linking-within-module-documentation
                                clean_line_of_doco = re.sub('[ILUCMB]\((.+?)\)','`\g<1>`',clean_line_of_doco) 

                                argument['description'] = argument['description'] + '\n' + clean_line_of_doco
                        argument['description'] = argument['description'].strip()
                    else:
                        argument['description'] = str(option.get('description'))

                    # if arg is deprecicated skip it
                    if argument['description'].startswith('`Deprecated'):
                        print("Skipping arg %s as it is Deprecated" % str(arg))
                        continue

                    if option.get('required') == True:
                        argument['required'] = True

                    if option.get('default') is not None:
                        argument['defaultValue'] = str(option.get('default'))

                    if option.get('choices') is not None:
                        argument['predefined'] = []
                        argument['auto'] = "PREDEFINED"
                        for choice in option.get('choices'):
                            argument['predefined'].append(str(choice))

                    if option.get('type') in ["list", "dict"]:
                        argument['isArray'] = True

                    command['arguments'].append(argument)

            # Outputs
            command['outputs'] = []
            if returndocs is not None:
                returndocs_dict = yaml.load(returndocs, Loader=yaml.Loader)
                if returndocs_dict is not None:
                    for output, details in returndocs_dict.items():
                        output_to_add = {}
                        if details is not None:
                            output_to_add['contextPath'] = str("%s.%s.%s" % (integration['name'], ansible_module, output))

                            # remove ansible link markup 
                            # https://docs.ansible.com/ansible/latest/dev_guide/developing_modules_documenting.html#linking-within-module-documentation
                            if type(details.get('description')) == list:
                                # Do something if it is a list
                                output_to_add['description'] = ""
                                for line in details.get('description'):
                                    clean_line_of_description = re.sub('[ILUCMB]\((.+?)\)','`\g<1>`', line) 
                                    output_to_add['description'] = output_to_add['description'] + "\n" + clean_line_of_description
                            else:
                                clean_line_of_description = re.sub('[ILUCMB]\((.+?)\)','`\g<1>`',str(details.get('description'))) 
                                output_to_add['description'] = clean_line_of_description

                            if details.get('type') == "str":
                                output_to_add['type'] = "string"
                            
                            elif details.get('type') == "int":
                                output_to_add['type'] = "number"

                            # Don't think Ansible has any kind of datetime attribute but just in case...
                            elif details.get('type') == "datetime":
                                output_to_add['type'] = "date"

                            elif details.get('type') == "bool":
                                output_to_add['type'] = "boolean"

                            else:  # If the output is any other type it doesn't directly map to a XSOAR type
                                output_to_add['type'] = "unknown"  
                            command['outputs'].append(output_to_add)                

            commands.append(command)

            # Create example XSOAR command
            try: 
                examples_dict = yaml.load(examples, Loader=yaml.Loader)
            # Sometimes there is more than one yaml doc in examples, not sure why. Lets grab just the first if that happens
            except yaml.composer.ComposerError as e:  
                examples_dict = list(yaml.load_all(examples, Loader=yaml.Loader))[0]
            if examples_dict is not None:
                if type(examples_dict) == list:
                    examples_dict = examples_dict[0]  # If there are multiple exmaples just use the first
                # Get actual example
                examples_dict = examples_dict.get(str(ansible_module))
                example_command = "!" + command['name'] + " "  # Start of command
                if integration_def.get('hostbasedtarget') in ("ssh", "winrm", "nxos", "ios"):  # Add a example host target
                    example_command += "host=\"192.168.1.125\" "
                if examples_dict is not None:
                    for arg, value in examples_dict.items():
                        # Skip args that the definition says to ignore
                        if integration_def.get('ignored_args') is not None:
                            if arg in integration_def.get('ignored_args'):
                                continue
                        value = str(value).replace("\n", "\"")
                        value = str(value).replace("\\", "\\\\")
                        example_command += "%s=\"%s\" " % (arg, value)

                command_examples.append(example_command + "\n")



        
        # Generate python script
        integration_script = '''import json
import traceback
import ansible_runner
import ssh_agent_setup
from typing import Dict, cast

import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401

# Import Generated code
from AnsibleApiModule import *  # noqa: E402


def generic_ansible(integration_name, command, args: Dict[str, Any]) -> CommandResults:

    readable_output = ""
    sshkey = ""
    fork_count = 1   # default to executing against 1 host at a time

    if args.get('concurrency'):
        fork_count = cast(int, args.get('concurrency'))

    inventory: Dict[dict, list, str] = {}
    inventory['all'] = {}
    inventory['all']['hosts'] = {}
    '''

        if integration_def.get('hostbasedtarget') is not None:
            integration_script +='''
    if type(args['host']) is list:
        # host arg can be a array of multiple hosts
        hosts = args['host']
    else:
        # host arg could also be csv
        hosts = [host.strip() for host in args['host'].split(',')]

    for host in hosts:
        new_host = {}
        new_host['ansible_host'] = host

        if ":" in host:
            address = host.split(':')
            new_host['ansible_port'] = address[1]
            new_host['ansible_host'] = address[0]
        else:
            new_host['ansible_host'] = host
            if demisto.params().get('port'):
                new_host['ansible_port'] = demisto.params().get('port')
        '''
        else:
            # This must be a module intended to run on localhost
            integration_script +='''
    inventory['all']['hosts']['localhost'] = {}
    inventory['all']['hosts']['localhost']['ansible_connection'] = 'local'
            '''


        if integration_def.get('hostbasedtarget') == "ssh":
            integration_script +='''# Linux

        # Different credential options
        # SSH Key saved in credential manager selection
        if demisto.params().get('creds', {}).get('credentials').get('sshkey'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            sshkey = demisto.params().get('creds', {}).get('credentials').get('sshkey')

            new_host['ansible_user'] = username

        # Password saved in credential manager selection
        elif demisto.params().get('creds', {}).get('credentials').get('password'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            password = demisto.params().get('creds', {}).get('credentials').get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        # username/password individually entered
        else:
            username = demisto.params().get('creds', {}).get('identifier')
            password = demisto.params().get('creds', {}).get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        inventory['all']['hosts'][host] = new_host'''
        elif integration_def.get('hostbasedtarget') == "winrm":
            integration_script +='''# Windows

        # Different credential options
        ## Password saved in credential manager selection
        if demisto.params().get('creds', {}).get('credentials').get('password'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            password = demisto.params().get('creds', {}).get('credentials').get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        ## username/password individually entered
        else:
            username = demisto.params().get('creds', {}).get('identifier')
            password = demisto.params().get('creds', {}).get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        new_host['ansible_connection'] = "winrm"
        new_host['ansible_winrm_transport'] = "ntlm"
        new_host['ansible_winrm_server_cert_validation'] = "ignore"

        inventory['all']['hosts'][host] = new_host'''
        elif integration_def.get('hostbasedtarget') == "ios":
            integration_script +='''# Cisco IOS

        # Different credential options
        # SSH Key saved in credential manager selection
        sshkey = ""
        if demisto.params().get('creds', {}).get('credentials').get('sshkey'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            sshkey = demisto.params().get('creds', {}).get('credentials').get('sshkey')

            new_host['ansible_user'] = username

        # Password saved in credential manager selection
        elif demisto.params().get('creds', {}).get('credentials').get('password'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            password = demisto.params().get('creds', {}).get('credentials').get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        # username/password individually entered
        else:
            username = demisto.params().get('creds', {}).get('identifier')
            password = demisto.params().get('creds', {}).get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        new_host['ansible_connection'] = 'network_cli'
        new_host['ansible_network_os'] = 'ios'
        new_host['ansible_become'] = 'yes'
        new_host['ansible_become_method'] = 'enable'
        inventory['all']['hosts'][host] = new_host'''
        elif integration_def.get('hostbasedtarget') == "nxos":
            integration_script +='''# Cisco NXOS

        # Different credential options
        # SSH Key saved in credential manager selection
        sshkey = ""
        if demisto.params().get('creds', {}).get('credentials').get('sshkey'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            sshkey = demisto.params().get('creds', {}).get('credentials').get('sshkey')

            new_host['ansible_user'] = username

        # Password saved in credential manager selection
        elif demisto.params().get('creds', {}).get('credentials').get('password'):
            username = demisto.params().get('creds', {}).get('credentials').get('user')
            password = demisto.params().get('creds', {}).get('credentials').get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        # username/password individually entered
        else:
            username = demisto.params().get('creds', {}).get('identifier')
            password = demisto.params().get('creds', {}).get('password')

            new_host['ansible_user'] = username
            new_host['ansible_password'] = password

        new_host['ansible_connection'] = 'network_cli'
        new_host['ansible_network_os'] = 'nxos'
        new_host['ansible_become'] = 'yes'
        new_host['ansible_become_method'] = 'enable'
        inventory['all']['hosts'][host] = new_host'''

        integration_script += '''
    module_args = ""
    # build module args list
    for arg_key, arg_value in args.items():
        # skip hardcoded host arg, as it doesn't related to module
        if arg_key == 'host':
            continue

        module_args += "%s=\\"%s\\" " % (arg_key, arg_value)'''

        if integration_def.get('hostbasedtarget') == None: 
            integration_script += '''
    # If this isn't host based, then all the integratation parms will be used as command args
    for arg_key, arg_value in demisto.params().items():
        module_args += "%s=\\"%s\\" " % (arg_key, arg_value)

        '''

        integration_script += '''

    r = ansible_runner.run(inventory=inventory, host_pattern='all', module=command, quiet=True,
                           omit_event_data=True, ssh_key=sshkey, module_args=module_args, forks=fork_count)

    results = []
    for each_host_event in r.events:
        # Troubleshooting
        # demisto.log("%s: %s\\n" % (each_host_event['event'], each_host_event))
        if each_host_event['event'] in ["runner_on_ok", "runner_on_unreachable", "runner_on_failed"]:

            # parse results

            result = json.loads('{' + each_host_event['stdout'].split('{', 1)[1])
            host = each_host_event['stdout'].split('|', 1)[0].strip()
            status = each_host_event['stdout'].replace('=>', '|').split('|', 3)[1]

            # if successful build outputs
            if each_host_event['event'] == "runner_on_ok":
                if 'fact' in command:
                    result = result['ansible_facts']
                else:
                    if result.get(command) is not None:
                        result = result[command]
                    else:
                        result.pop("ansible_facts", None)

                result = rec_ansible_key_strip(result)

                if host != "localhost":
                    readable_output += "# %s - %s\\n" % (host, status)
                else:
                    # This is integration is not host based
                    readable_output += "# %s\\n" % status

                readable_output += dict2md(result)

                # add host and status to result
                result['host'] = host
                result['status'] = status

                results.append(result)
            if each_host_event['event'] == "runner_on_unreachable":
                msg = "Host %s unreachable\\nError Details: %s" % (host, result)
                return_error(msg)

            if each_host_event['event'] == "runner_on_failed":
                msg = "Host %s failed running command\\nError Details: %s" % (host, result)
                return_error(msg)'''
        if integration_def.get('hostbasedtarget') == None:
            integration_script += '''
    # This is integration is not host based and always runs against localhost
    results = results[0]
    '''
        integration_script += '''
    return CommandResults(
        readable_output=readable_output,
        outputs_prefix=integration_name + '.' + command,
        outputs_key_field='',
        outputs=results
    )


# MAIN FUNCTION


def main() -> None:
    """main function, parses params and runs command functions

    :return:
    :rtype:
    """

    # SSH Key integration requires ssh_agent to be running in the background
    ssh_agent_setup.setup()

    try:

        if demisto.command() == 'test-module':
            # This is the call made when pressing the integration Test button.
            return_results('ok')'''
        
        for ansible_module in integration_def.get('ansible_modules'):

            if integration_def.get('command_prefix') is not None:
                command_prefix = integration_def.get('command_prefix')
            else:
                if len(integration_def.get('name').split(' ')) == 1:  # If the definition `name` is single word then trust the caps
                    command_prefix = integration['name'].lower()
                else:
                    command_prefix = spinalcase(integration['name'])

            demisto_command = ""
            if not spinalcase(ansible_module).startswith(command_prefix + '-'):
                demisto_command = command_prefix + '-' + spinalcase(ansible_module)
            else:
                demisto_command = spinalcase(ansible_module)

            integration_script += "\n        elif demisto.command() == '%s':\n            return_results(generic_ansible('%s', '%s', demisto.args()))" % (demisto_command, integration['name'].lower(), ansible_module,)

        integration_script += '''
    # Log exceptions and return errors
    except Exception as e:
        demisto.error(traceback.format_exc())  # print the traceback
        return_error(f'Failed to execute {demisto.command()} command.\\nError:\\n{str(e)}')


# ENTRY POINT


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()'''
    
        
        integration['script'] = {
            'type' : "python",
            'subtype' : "python3",
            'dockerimage' : "demisto/ansible-runner:%s" % ANSIBLE_RUNNER_DOCKER_VERSION,
            'runonce' : False,
            'commands': commands,
            'script' : "",    # Output as a seperate .py file
        }

        # Save output files
        output_path = os.path.join(OUTPUT_DIR, integration['name'])  # Create a folder per intergration
        Path(output_path).mkdir(parents=True, exist_ok=True)  # Make the output path if it doesn't already exist

        # save the .py
        filename = os.path.join(output_path, integration['name'] + '.py')
        with open(filename, 'w') as outfile:
            outfile.writelines(integration_script)

        # save the .yml definition
        filename = os.path.join(output_path, integration['name'] + '.yml')
        with open(filename, 'w') as outfile:
            yaml.dump(integration, outfile, default_flow_style=False)

        # save the .png 
        if integration_def.get('image') is not None:
            filename = os.path.join(output_path, integration['name'] + '_image.png')
            with open(filename, 'wb') as outfile:
                outfile.write(base64.b64decode(integration_def.get('image')))
        
        # save the example commands
        filename = os.path.join(output_path, integration['name'] + '_commands.txt')
        with open(filename, 'w') as outfile:
            outfile.writelines(command_examples)
        print("Integration: %s saved to folder: %s" % (integration['display'], output_path))