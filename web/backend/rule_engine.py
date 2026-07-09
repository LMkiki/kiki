import re

CITY_DISTRICT_MAP = {
    "杭州市": ["上城区", "拱墅区", "西湖区", "滨江区", "萧山区", "余杭区", "临平区", "钱塘区",
              "富阳区", "临安区", "桐庐县", "淳安县", "建德市"],
    "宁波市": ["海曙区", "江北区", "北仑区", "镇海区", "鄞州区", "奉化区",
              "余姚市", "慈溪市", "宁海县", "象山县"],
    "温州市": ["鹿城区", "龙湾区", "瓯海区", "洞头区", "瑞安市", "乐清市",
              "永嘉县", "平阳县", "苍南县", "文成县", "泰顺县"],
    "嘉兴市": ["南湖区", "秀洲区", "海宁市", "平湖市", "桐乡市", "嘉善县", "海盐县"],
    "湖州市": ["吴兴区", "南浔区", "德清县", "长兴县", "安吉县"],
    "绍兴市": ["越城区", "柯桥区", "上虞区", "诸暨市", "嵊州市", "新昌县"],
    "金华市": ["婺城区", "金东区", "兰溪市", "义乌市", "东阳市", "永康市",
              "武义县", "浦江县", "磐安县"],
    "衢州市": ["柯城区", "衢江区", "江山市", "龙游县", "常山县", "开化县"],
    "舟山市": ["定海区", "普陀区", "岱山县", "嵊泗县"],
    "台州市": ["椒江区", "黄岩区", "路桥区", "临海市", "温岭市", "玉环市",
              "天台县", "仙居县", "三门县"],
    "丽水市": ["莲都区", "龙泉市", "青田县", "缙云县", "遂昌县",
              "松阳县", "云和县", "庆元县", "景宁畲族自治县"],
}

DISTRICT_TO_CITY = {}
for _city, _districts in CITY_DISTRICT_MAP.items():
    for _d in _districts:
        DISTRICT_TO_CITY[_d] = _city

PLATE_CITY_MAP = {
    "A": "杭州市", "B": "宁波市", "C": "温州市", "D": "绍兴市",
    "E": "湖州市", "F": "嘉兴市", "G": "金华市", "H": "衢州市",
    "J": "台州市", "K": "丽水市", "L": "舟山市",
}

PLATE_PATTERN = re.compile(r"^浙[A-HJ-NP-Z][0-9A-Z]{5,6}$")
MOTORCYCLE_PATTERN = re.compile(r"^浙[A-HJ-NP-Z][0-9A-Z]{4}$")

ACCIDENT_KEYWORDS = ["撞", "事故", "剐蹭", "追尾", "肇事", "碰撞", "刮擦", "碰瓷", "车祸", "撞击", "事故现场", "交通事故"]
HUMAN_KEYWORDS = ["人工", "客服", "转人工"]


def validate_plate(plate_no):
    if not plate_no or not plate_no.strip():
        return False, "车牌号不能为空"
    plate = plate_no.strip().replace("·", "").replace("-", "").replace(" ", "")
    if not plate.startswith("浙"):
        return False, "仅支持浙江省号牌（浙开头）"
    if "临" in plate:
        return False, "不支持临时号牌"
    if "WJ" in plate or "wj" in plate:
        return False, "不支持武警号牌"
    if plate.endswith("警"):
        return False, "不支持警车号牌"
    if plate.endswith("消"):
        return False, "不支持消防救援号牌"
    if plate.endswith("救"):
        return False, "不支持救护车号牌"
    if "军" in plate:
        return False, "不支持军车号牌"
    if MOTORCYCLE_PATTERN.match(plate):
        return False, "不支持摩托车号牌"
    if not PLATE_PATTERN.match(plate):
        return False, "车牌格式不正确"
    return True, ""


def check_accident(reason):
    if not reason:
        return False, ""
    for kw in ACCIDENT_KEYWORDS:
        if kw in reason:
            return True, "当前情况涉及交通事故，请拨打122处理"
    return False, ""


def get_plate_city(plate_no):
    if not plate_no or len(plate_no) < 2:
        return ""
    letter = plate_no.strip().replace("·", "").replace("-", "").replace(" ", "")
    if not letter.startswith("浙") or len(letter) < 2:
        return ""
    return PLATE_CITY_MAP.get(letter[1], "")


def check_address(address, plate_city=""):
    if not address or not address.strip():
        return False, "", "地址不能为空"
    addr = address.strip()
    found_city = None
    for city in CITY_DISTRICT_MAP:
        if city in addr:
            found_city = city
            break
    found_district = None
    found_district_city = None
    for district, city in DISTRICT_TO_CITY.items():
        if district in addr:
            found_district = district
            found_district_city = city
            break
    if not found_district:
        return False, "", "地址中未识别到浙江省内区县"
    if found_city:
        if found_district not in CITY_DISTRICT_MAP[found_city]:
            return False, "", "地址中市与区县不匹配"
        return True, f"浙江省{found_city}{found_district}", ""
    if plate_city and plate_city in CITY_DISTRICT_MAP and found_district in CITY_DISTRICT_MAP[plate_city]:
        return True, f"浙江省{plate_city}{found_district}", ""
    return True, f"浙江省{found_district_city}{found_district}", ""


def need_human(content, consecutive_failures=0):
    if content:
        for kw in HUMAN_KEYWORDS:
            if kw in content:
                return True
    return consecutive_failures >= 3
