from mininet.topo import Topo
from mininet.link import TCLink



class SpineLeafTopo(Topo):
	"""Spine-Leaf topology with 2 spines (S1,S2), 3 leaves (L1..L3),
	and 3 hosts per leaf named H<leaf><host> (e.g., H11, H12, H13).
	All hosts are in the same /24 subnet for L2 connectivity across fabric.
	"""

	def build(self, num_spines=2, num_leaves=3, hosts_per_leaf=3):
		# Create spines named S1..Sn
		spines = []
		for s in range(1, num_spines + 1):
			# Stable DPIDs
			dpid = "{:016x}".format(s)
			sp = self.addSwitch("s{}".format(s), dpid=dpid, protocols='OpenFlow13')
			spines.append(sp)

		# Create leaves named L1..Lm
		leaves = []
		for l in range(1, num_leaves + 1):
			sw_id = num_spines + l
			dpid = "{:016x}".format(sw_id)
			leaf = self.addSwitch("l{}".format(l), dpid=dpid, protocols='OpenFlow13')
			leaves.append(leaf)

			# Add hosts for this leaf named H<leaf><host>
			for h in range(1, hosts_per_leaf + 1):
				# IP scheme: 10.0.0.<leaf><host>/24 for L2 communication across leaves
				last_octet = int("{}{}".format(l, h))
				host = self.addHost(
					"h{}{}".format(l, h),
					ip="10.0.0.{}".format(last_octet) + "/24"
				)
				self.addLink(leaf, host, cls=TCLink, bw=1)

		# Connect each leaf to all spines
		for leaf in leaves:
			for spine in spines:
				# Use higher bandwidth on fabric links
				self.addLink(leaf, spine, cls=TCLink, bw=10, delay='1ms')

topos = { 'spineleaf': SpineLeafTopo }


