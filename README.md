# Ansible-for-XSOAR
Tool to generate Palo Alto XSOAR integrations based on Ansible modules. 
This tool is one part of two Ansible translation wrappers, it generates the XSOAR Integration definition and Python code. The second part of this the Ansible translation is in the form of a Ansible-Runner Docker container which is run under the covers of the XSOAR engine. This container has been accepted into the XSOAR content, and can be found [here](https://github.com/demisto/dockerfiles/tree/master/docker/ansible-runner).

This tool was written for my Automation Rising 2020 SOAR Hackathon submission; [1+1 = 3 Supercharging XSOAR with Ansible.](https://devpost.com/software/serge-s-placeholder-submission). The code here is hacky and has a number of hardcoded paths as the tool itself was not my submission, it simply generates the Ansible XSOAR integrations which were a component in my content pack.

At a high level this tool parses the Ansible module documentation to generate equivilent XSOAR command definitions. It then generates the wrapper python code to enable those Ansible modules to be usable in XSOAR via the Ansible-Runner container.

# Usage
1. Write a definitions.yml to describes the desired XSOAR integration(s). In the repo is the definitions file used for the competition.
2. Clone the [Ansible git repo](https://github.com/ansible/ansible) in the same directory as this tool. This tool expects to find the Ansible module python code in ./ansible/lib/ansible/modules/. Note this tool was written for Ansible 2.9 and is untested with Ansible Galaxies in 2.10.
3. Run ansible_module2demisto_integration.py This will generate and save the resulting XSOAR intergrations in the output folder.

# Limitations
* Ansible modules that use environment variables are unsupported as this tool does not set environment variables yet
* Authentication is limited to only the following options:
    1. SSH private key
    2. (preferably) XSOAR integration instance based inputs eg Username/Password fields. Instance fields can be definied in definitions.yml
    3. XSOAR credential manager of the above
* File copy Ansible modules can only operate in 'remote src to remote dest' mode. They cannot be used to copy files to the XSOAR engine server.
* Ansible Shell/Command modules that use free-form syntax for the command don't get parsed correctly and as a result ommited in the intial release of this tool
* Ansible modules with nested command parameters do not do not have the nested parameters visible in XSOAR
* MANY Ansible modules do not document their outputs. As a result the XSOAR definition for the context output may be ommited or incomplete. Best to run the command and see the output. Some Ansible modules have a dynamic output.
