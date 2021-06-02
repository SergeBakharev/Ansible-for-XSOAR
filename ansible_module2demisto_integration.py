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
ANSIBLE_RUNNER_DOCKER_VERSION = '1.0.0.20435'  # The tag of demisto/ansible-runner to use
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
            config['display'] = "Concurrency Factor"
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
            command['description'] = str(doc.get('short_description')) + "\n Further documentation available at " + module_online_help
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
        integration_script = '''import traceback
import ssh_agent_setup
import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401

# Import Generated code
from AnsibleApiModule import *  # noqa: E402

'''

        if integration_def.get('hostbasedtarget') is not None:
            integration_script +="host_type =  '%s'" % integration_def.get('hostbasedtarget')
        else:
            integration_script +="host_type =  'local'"
        
        integration_script += '''

# MAIN FUNCTION


def main() -> None:
    """main function, parses params and runs command functions

    :return:
    :rtype:
    """

    # SSH Key integration requires ssh_agent to be running in the background
    ssh_agent_setup.setup()

    # Common Inputs
    command = demisto.command()
    args = demisto.args()
    int_params = demisto.params()

    try:

        if command == 'test-module':
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

            integration_script += "\n        elif demisto.command() == '%s':\n            return_results(generic_ansible('%s', '%s', args, int_params, host_type))" % (demisto_command, integration['name'].lower(), ansible_module,)

        integration_script += '''
    # Log exceptions and return errors
    except Exception as e:
        demisto.error(traceback.format_exc())  # print the traceback
        return_error(f'Failed to execute {command} command.\nError:\n{str(e)}')


# ENTRY POINT


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()'''
    
        
        integration['script'] = {
            'type' : "python",
            'subtype' : "python3",
            'dockerimage' : "demisto/ansible-runner:%s" % ANSIBLE_RUNNER_DOCKER_VERSION,
            'runonce' : False,
            'commands': commands,
            'script' : "",    # Output as a separate .py file
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