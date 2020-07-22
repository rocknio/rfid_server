# coding: utf-8
from sqlalchemy import BigInteger, Column, Date, DateTime, Index, Integer, Numeric, SmallInteger, String, Table, Text, text
from sqlalchemy.dialects.mysql.types import MEDIUMBLOB
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()
metadata = Base.metadata


class TAppUser(Base):
    __tablename__ = 't_app_user'

    id = Column(Integer, primary_key=True)
    username = Column(String(20), unique=True)
    password = Column(String(50))
    userdesc = Column(String(200))
    create_time = Column(Date)
    supplier_id = Column(String(32))


class TAppVersion(Base):
    __tablename__ = 't_app_version'

    id = Column(Integer, primary_key=True)
    version_code = Column(Integer, nullable=False)
    version_name = Column(String(16))
    create_time = Column(DateTime)
    enable = Column(Integer, server_default=text("'0'"))


class TCaseInfo(Base):
    __tablename__ = 't_case_info'

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), nullable=False, unique=True)
    init_time = Column(DateTime)
    print_result = Column(Integer)


class TClientInfo(Base):
    __tablename__ = 't_client_info'

    id = Column(Integer, primary_key=True)
    client_id = Column(String(32), nullable=False, index=True)
    client_name = Column(String(64), nullable=False)
    client_desc = Column(String(256))
    contact_person = Column(String(32))
    address = Column(String(256))
    phone_number = Column(String(16))


class TColorDict(Base):
    __tablename__ = 't_color_dict'

    id = Column(Integer, primary_key=True)
    color = Column(String(16), nullable=False, unique=True)
    color_desc = Column(String(32), nullable=False)


class TEpcDetail(Base):
    __tablename__ = 't_epc_detail'

    id = Column(Integer, primary_key=True)
    sku = Column(String(32), nullable=False, index=True)
    epc = Column(String(32), nullable=False, index=True)
    print_date = Column(DateTime, index=True)
    received_date = Column(DateTime, index=True)
    ship_date = Column(DateTime, index=True)
    product_name = Column(String(64))
    supplier_id = Column(String(32), index=True)
    color = Column(String(32))
    size = Column(String(32))
    order_id = Column(String(32), index=True)
    goods_id = Column(String(32))
    brand_name = Column(String(32))
    print_result = Column(Integer)


class TListCountLog(Base):
    __tablename__ = 't_list_count_log'

    id = Column(Integer, primary_key=True)
    ship_id = Column(String(32), nullable=False)
    sku = Column(String(32), nullable=False)
    ship_quantity = Column(Integer, nullable=False)
    counted_quantity = Column(Integer)
    count_date = Column(DateTime)


class TOperator(Base):
    __tablename__ = 't_operator'

    operatorid = Column(Integer, primary_key=True)
    account = Column(String(50), nullable=False)
    name = Column(String(80), nullable=False)
    password = Column(String(32), nullable=False)
    mobile = Column(String(15))
    email = Column(String(128))
    roleid = Column(String(32), nullable=False)
    status = Column(Numeric(2, 0), server_default=text("'0'"))
    createid = Column(Numeric(9, 0), nullable=False)
    createtime = Column(DateTime, nullable=False)
    supplier_id = Column(String(32))


class TPrintCodeSetting(Base):
    __tablename__ = 't_print_code_setting'

    id = Column(Integer, primary_key=True)
    tag_type = Column(String(32), nullable=False)
    code = Column(String(128))
    start_pos_x = Column(Integer)
    start_pos_y = Column(Integer)
    rotation = Column(Integer)
    height = Column(Integer)


class TPrintFontSetting(Base):
    __tablename__ = 't_print_font_setting'

    id = Column(Integer, primary_key=True)
    dpm = Column(String(16))
    font_name = Column(String(32))
    font_height = Column(Integer)
    font_width = Column(Integer)


class TPrintLineSetting(Base):
    __tablename__ = 't_print_line_setting'

    id = Column(Integer, primary_key=True)
    tag_type = Column(String(32), nullable=False)
    length = Column(Integer)
    bold = Column(Numeric(11, 1))
    start_pos_x = Column(Integer)
    start_pos_y = Column(Integer)
    rotation = Column(Integer)


class TPrintTagSetting(Base):
    __tablename__ = 't_print_tag_setting'

    id = Column(Integer, primary_key=True)
    tag_type = Column(String(32), nullable=False)
    act_height = Column(Integer)
    act_width = Column(Integer)
    rotation = Column(Integer)
    pad_top = Column(Integer)
    pad_bottom = Column(Integer)
    pad_left = Column(Integer)
    pad_right = Column(Integer)


class TPrintTextSetting(Base):
    __tablename__ = 't_print_text_setting'

    id = Column(Integer, primary_key=True)
    tag_type = Column(String(32), nullable=False)
    text = Column(String(512))
    start_pos_x = Column(Integer)
    start_pos_y = Column(Integer)
    rotation = Column(Integer)
    fontId = Column(Integer)
    height_enlarge = Column(Integer)
    width_enlarge = Column(Integer)


class TPrinter(Base):
    __tablename__ = 't_printer'

    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    host = Column(String(32))
    port = Column(Integer)
    dpm = Column(Integer)
    lang = Column(String(32))


class TPurchaseOrder(Base):
    __tablename__ = 't_purchase_order'

    id = Column(Integer, primary_key=True)
    order_id = Column(String(32), nullable=False, unique=True)
    order_name = Column(String(64))
    supplier_id = Column(String(32))
    purchase_quantity = Column(Integer)
    received_quantity = Column(Integer)
    purchase_date = Column(DateTime, index=True)
    received_date = Column(DateTime, index=True)
    status = Column(Integer, index=True)


class TPurchaseOrderSku(Base):
    __tablename__ = 't_purchase_order_sku'

    id = Column(Integer, primary_key=True)
    order_id = Column(String(32), nullable=False, index=True)
    product_name = Column(String(64))
    sku = Column(String(16), nullable=False, index=True)
    color = Column(String(16))
    size = Column(String(8))
    purchase_quantity = Column(Integer)
    received_quantity = Column(Integer)


class TReceiptBatchCase(Base):
    __tablename__ = 't_receipt_batch_case'

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), nullable=False, index=True)
    batch_id = Column(String(32), nullable=False, index=True)
    order_id = Column(String(32), index=True)
    ship_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer)
    status = Column(Integer, nullable=False, index=True)


class TReceiptBatchCaseSkuStatistic(Base):
    __tablename__ = 't_receipt_batch_case_sku_statistics'

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), nullable=False, index=True)
    sku = Column(String(32), nullable=False)
    ship_quantity = Column(Integer, nullable=False)
    pre_receipt_quantity = Column(Integer, server_default=text("'0'"))
    storage_quantity = Column(Integer, server_default=text("'0'"))
    return_quantity = Column(Integer, server_default=text("'0'"))
    received_date = Column(DateTime)
    status = Column(SmallInteger)
    remark = Column(String(200), server_default=text("''"))
    validate = Column(Integer)
    validate_date = Column(DateTime)


class TReceiptDetail(Base):
    __tablename__ = 't_receipt_detail'

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), nullable=False)
    batch_id = Column(String(32), nullable=False)
    order_id = Column(String(32))
    sku = Column(String(16), nullable=False)
    epc = Column(String(32), nullable=False)
    status = Column(SmallInteger, server_default=text("'0'"))


class TReceiptDetailHistory(Base):
    __tablename__ = 't_receipt_detail_history'

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), nullable=False)
    batch_id = Column(String(32), nullable=False)
    order_id = Column(String(32))
    sku = Column(String(16), nullable=False)
    epc = Column(String(32), nullable=False, index=True)
    status = Column(SmallInteger, server_default=text("'0'"))


class TReceiptInfo(Base):
    __tablename__ = 't_receipt_info'

    id = Column(Integer, primary_key=True)
    batch_id = Column(String(32), nullable=False, index=True)
    order_id = Column(String(32), index=True)
    ship_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer)
    ship_date = Column(DateTime)
    received_date = Column(DateTime)
    supplier_id = Column(String(32))
    app_user = Column(String(32))
    status = Column(Integer)


class TReceiptScanDetail(Base):
    __tablename__ = 't_receipt_scan_detail'

    id = Column(Integer, primary_key=True)
    epc = Column(String(32))
    trans_id = Column(String(32))
    sku = Column(String(32))


class TReceiptScanLog(Base):
    __tablename__ = 't_receipt_scan_log'
    __table_args__ = (
        Index('idx_case_sku', 'case_id', 'sku'),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(String(160))
    case_id = Column(String(32))
    sku = Column(String(32))
    ship_quantity = Column(Integer)
    received_quantity = Column(Integer)
    receive_date = Column(DateTime)
    status = Column(SmallInteger)
    trans_id = Column(String(32))


t_t_role = Table(
    't_role', metadata,
    Column('roleid', String(32), nullable=False),
    Column('rolename', String(128)),
    Column('roledesc', String(256)),
    Column('creatorid', Numeric(9, 0))
)


t_t_role_perm = Table(
    't_role_perm', metadata,
    Column('roleid', String(32), nullable=False),
    Column('permid', String(32), nullable=False)
)


class TShipDetail(Base):
    __tablename__ = 't_ship_detail'

    id = Column(Integer, primary_key=True)
    ship_id = Column(String(32))
    sku = Column(String(16))
    epc = Column(String(32))


class TShipDetailHistory(Base):
    __tablename__ = 't_ship_detail_history'

    id = Column(Integer, primary_key=True)
    ship_id = Column(String(32))
    sku = Column(String(16))
    epc = Column(String(32))


class TShipOrder(Base):
    __tablename__ = 't_ship_order'

    id = Column(Integer, primary_key=True)
    ship_id = Column(String(32), nullable=False)
    ship_date = Column(DateTime)
    ship_quantity = Column(Integer)
    status = Column(Integer)
    client_id = Column(String(32))
    type = Column(SmallInteger)


class TShipOrderDetail(Base):
    __tablename__ = 't_ship_order_detail'

    id = Column(Integer, primary_key=True)
    ship_id = Column(String(32), nullable=False)
    product_name = Column(String(64))
    sku = Column(String(16), nullable=False)
    color = Column(String(16))
    size = Column(String(8))
    ship_quantity = Column(Integer, server_default=text("'0'"))
    shipped_quantity = Column(Integer, server_default=text("'0'"))
    ship_date = Column(DateTime)


class TSizeDict(Base):
    __tablename__ = 't_size_dict'

    id = Column(Integer, primary_key=True)
    size = Column(String(16), nullable=False, index=True)
    size_desc = Column(String(32), nullable=False)


class TSkuInfo(Base):
    __tablename__ = 't_sku_info'

    id = Column(Integer, primary_key=True)
    sku = Column(String(32), nullable=False, unique=True)
    product_name = Column(String(64))
    color = Column(String(16))
    size = Column(String(8))


class TSkuSequence(Base):
    __tablename__ = 't_sku_sequence'

    id = Column(Integer, primary_key=True)
    sequence_name = Column(String(32), nullable=False)
    start_num = Column(Integer, nullable=False)
    max_num = Column(Integer, nullable=False)
    current_num = Column(Integer, nullable=False)
    step = Column(Integer, nullable=False)


class TStatusDict(Base):
    __tablename__ = 't_status_dict'
    __table_args__ = (
        Index('idx_status_dict_status', 'table_name', 'status'),
    )

    id = Column(Integer, primary_key=True)
    table_name = Column(String(32), nullable=False)
    status = Column(Integer, nullable=False)
    status_desc = Column(String(64), nullable=False)


class TSupplierInfo(Base):
    __tablename__ = 't_supplier_info'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(String(32), nullable=False, index=True)
    supplier_name = Column(String(64), nullable=False)
    supplier_desc = Column(String(256))
    contact_person = Column(String(32))
    address = Column(String(256))
    phone_number = Column(String(16))
    username = Column(String(32))
    password = Column(String(32))


class TTagPrintResult(Base):
    __tablename__ = 't_tag_print_result'

    id = Column(Integer, primary_key=True)
    tag_type = Column(String(32))
    order_no = Column(String(64))
    sku = Column(String(64))
    epc = Column(String(64), index=True)
    result = Column(Integer)
    result_msg = Column(String(128))
    print_time = Column(DateTime)


class TTagTemplate(Base):
    __tablename__ = 't_tag_template'

    id = Column(Integer, primary_key=True)
    name = Column(String(32))
    zpl = Column(Text)
    brand = Column(String(32))
    type = Column(String(16))
    oncezpl = Column(Text)
    lang = Column(String(32))


class TTagTemplatePic(Base):
    __tablename__ = 't_tag_template_pic'

    id = Column(BigInteger, primary_key=True)
    name = Column(String(32))
    pic = Column(MEDIUMBLOB)
    template_id = Column(BigInteger)


class TTmMachine(Base):
    __tablename__ = 't_tm_machine'

    id = Column(Integer, primary_key=True)
    tm_code = Column(String(20))
    tm_name = Column(String(20))
    tm_desc = Column(String(100))
    tm_floor = Column(String(10))
    tm_area = Column(String(20))
    tm_ip = Column(String(20))


class TWmsSyncLog(Base):
    __tablename__ = 't_wms_sync_logs'

    id = Column(Integer, primary_key=True)
    optime = Column(DateTime, nullable=False)
    status = Column(Integer, nullable=False)
    unit_id = Column(String(32), nullable=False)
    req_body = Column(Text)
    res_body = Column(String(500), nullable=False)
    type = Column(String(4), nullable=False)
    trans_id = Column(String(32), nullable=False, server_default=text("''"))


class TReturnInfo(Base):
    __tablename__ = 't_returned_info'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(String(32))
    supplier_name = Column(String(32))
    order_id = Column(String(32))
    case_id = Column(String(32))
    sku = Column(String(32))
    epc = Column(String(32))
    brand_name = Column(String(32))
    color = Column(String(32))
    size = Column(String(32))
    received_date = Column(DateTime)
    return_time = Column(DateTime)
    exit_time = Column(DateTime)
    return_user = Column(String(32))
    return_reason = Column(String(32))
    return_status = Column(Integer)
    postnumber = Column(String(128))


class TScmSyncLog(Base):
    __tablename__ = 't_scm_sync_logs'

    id = Column(Integer, primary_key=True)
    transid = Column(String(32), nullable=False, server_default=text("''"))
    entry_order_code = Column(String(32))
    operate_time = Column(DateTime, nullable=False)
    supplier_code = Column(String(32))
    type = Column(String(32))
    status = Column(Integer, nullable=False)
    req_body = Column(Text)
    res_body = Column(String(500), nullable=False)
