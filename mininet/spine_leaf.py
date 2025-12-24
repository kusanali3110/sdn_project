import os
import sys
import yaml
from mininet.topo import Topo

class SpineLeafTopo(Topo):
    def build(self, config_file="network_config.yaml"):
        with open(config_file, "r") as file:
            config = yaml.safe_load(file)

        for switch_config in config["switches"]:
            self.addSwitch(switch_config["name"])

        for link_config in config["links"]:
            self.addLink(
                link_config["source"],
                link_config["target"],
                port1=link_config["source_port"],
                port2=link_config["target_port"],
            )

        for host_config in config["hosts"]:
            self.addHost(
                host_config["name"],
                ip=host_config["ip"],
                mac=host_config["mac"],
                defaultRoute=host_config["default_route"],
            )
            self.addLink(
                host_config["name"],
                host_config["connected_to"],
                port1=host_config["port"]
            )

topos = {"spineleaf": SpineLeafTopo}