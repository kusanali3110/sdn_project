**Start Mininet with custom topology:**
```
mn --custom spine_leaf.py --topo spineleaf --controller remote,ip=ryu,port=6653 --switch ovsk,protocols=OpenFlow13
```

**After Mininet starts, in Mininet CLI**
```
# Simulate traffic between hosts
mininet> py exec(open('/app/traffic_generator.py').read())
```