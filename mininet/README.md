**Khởi động Mininet với custom topo:**
```
mn --custom spine_leaf.py --topo spineleaf --controller remote,ip=ryu,port=6653 --switch ovsk,protocols=OpenFlow13
```

**Sau khi tạo Mininet topo, tại Mininet CLI, chạy trình tạo traffic**
```
# Simulate traffic between hosts
mininet> py exec(open('/app/traffic_generator.py').read())
```