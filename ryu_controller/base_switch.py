from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3


class BaseSwitch(app_manager.RyuApp):
    """
    Base Switch Application bao gồm các hàm hữu dụng.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(BaseSwitch, self).__init__(*args, **kwargs)

    @staticmethod
    def add_flow(
        datapath,
        table_id,
        priority,
        match,
        inst,
        h_time=0,
        i_time=0,
        cookie=0,
        flags=0,
        buffer_id=None,
    ):
        """
        Tạo message FlowMod để thêm flow entry và trả về message.
        """

        parser = datapath.ofproto_parser
        msg = parser.OFPFlowMod(
            datapath=datapath,
            table_id=table_id,
            priority=priority,
            hard_timeout=h_time,
            idle_timeout=i_time,
            cookie=cookie,
            flags=flags,
            match=match,
            instructions=inst,
        )
        return msg

    @staticmethod
    def del_flow(
        datapath,
        table_id=-1,
        match=None,
        cookie=0,
        cookie_mask=-1,
        out_port=0,
        out_group=0,
    ):
        """
        Tạo message FlowMod để xóa flow entry và trả về message.
        """

        ofproto = datapath.ofproto
        out_port = out_port or ofproto.OFPP_ANY
        out_group = out_group or ofproto.OFPG_ANY
        table_id = table_id if table_id > -1 else ofproto.OFPTT_ALL
        cookie_mask = cookie_mask if cookie_mask > -1 else 0xFFFFFFFFFFFFFFFF

        parser = datapath.ofproto_parser
        msg = parser.OFPFlowMod(
            datapath=datapath,
            table_id=table_id,
            cookie=cookie,
            cookie_mask=cookie_mask,
            match=match,
            command=ofproto.OFPFC_DELETE,
            out_port=out_port,
            out_group=out_group,
        )
        return msg

    @staticmethod
    def forward_packet(datapath, data, in_port, out_port):
        """
        Trả về message PACKET_OUT để gửi packet đến một switch
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        actions = [parser.OFPActionOutput(out_port)]
        msg = [
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=data,
            )
        ]
        return msg

    @staticmethod
    def send_messages(datapath, msg_list, barrier=False):
        """
        Gửi tất cả messages đến switch, sau đó gửi message Barrier request, nếu yêu cầu.
        """

        for msg in msg_list:
            datapath.send_msg(msg)

        if barrier:
            # Gửi message Barrier request
            parser = datapath.ofproto_parser
            datapath.send_msg(parser.OFPBarrierRequest(datapath))