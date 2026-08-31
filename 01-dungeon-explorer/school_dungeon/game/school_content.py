from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchoolZone:
    subject: str
    location: str
    topics: tuple[str, ...]
    monster_forms: tuple[str, str, str]


SCHOOL_ZONES: tuple[SchoolZone, ...] = (
    SchoolZone(
        "体育", "失控体育馆",
        ("集合点名", "热身运动", "跳绳测验", "仰卧起坐", "足球训练", "篮球对抗", "排球垫球", "乒乓球台", "体能测试", "八百米终点"),
        ("体育委员", "失控器材", "迟到检查员"),
    ),
    SchoolZone(
        "音乐美术", "回声艺术楼",
        ("五线谱", "节拍训练", "合唱排练", "钢琴教室", "水彩颜料", "素描石膏", "透视练习", "色彩构成", "舞台彩排", "毕业汇演"),
        ("活化涂鸦", "异常回声", "石膏像"),
    ),
    SchoolZone(
        "生物", "增殖生态园",
        ("显微镜", "植物细胞", "动物细胞", "光合作用", "消化系统", "血液循环", "神经反射", "遗传图谱", "生态循环", "细胞母巢"),
        ("孢子团", "细胞团", "活化标本"),
    ),
    SchoolZone(
        "地理", "折叠地理室",
        ("经纬坐标", "等高线", "天气图", "季风气候", "河流地貌", "高原山脉", "沙漠绿洲", "海洋洋流", "板块边界", "大陆漂移"),
        ("自动地图", "异常气象图", "失控地貌模型"),
    ),
    SchoolZone(
        "历史", "逆行历史长廊",
        ("远古遗址", "青铜铭文", "诸侯烽火", "帝国长城", "丝路驿站", "盛世宫门", "旧都残卷", "航海时代", "工业钟楼", "错乱年表"),
        ("错乱残卷", "活化甲胄模型", "错乱年表"),
    ),
    SchoolZone(
        "化学", "沸腾化学楼",
        ("实验安全", "元素符号", "分子模型", "质量守恒", "酸碱指示", "金属反应", "溶液配制", "气体制取", "化学方程", "元素周期"),
        ("失控试剂", "分子模型", "异常反应"),
    ),
    SchoolZone(
        "物理", "超载物理楼",
        ("长度测量", "速度实验", "质量密度", "力与运动", "压力浮力", "声波走廊", "光学迷宫", "电路教室", "磁场禁区", "牛顿摆阵"),
        ("失控仪器", "错误定律", "能量异常"),
    ),
    SchoolZone(
        "英语", "异文语言楼",
        ("字母迷宫", "单词拼写", "名词复数", "介词陷阱", "一般时态", "完成时态", "从句回廊", "听力广播", "完形填空", "不规则动词"),
        ("语法错误", "错拼单词", "听力噪音"),
    ),
    SchoolZone(
        "语文", "墨痕语文楼",
        ("字音字形", "标点迷阵", "成语走廊", "病句诊室", "古诗碑林", "文言书库", "说明文室", "议论文厅", "作文考场", "阅读深渊"),
        ("失控墨迹", "飞散书页", "错误批注"),
    ),
    SchoolZone(
        "数学", "无解数学深渊",
        ("整数运算", "分数迷宫", "比例天平", "一次方程", "几何回廊", "函数阶梯", "概率转盘", "统计图室", "压轴题海", "最终考场"),
        ("跳动数字", "失控公式", "错误演算"),
    ),
)


MAJOR_BOSS_NAMES: dict[int, str] = {
    10: "永不结束的八百米",
    20: "失控的石膏乐团",
    30: "无限分裂的细胞母体",
    40: "大陆漂移巨龟",
    50: "篡改历史之王",
    60: "暴走元素周期表",
    70: "牛顿摆巨像",
    80: "不规则动词龙",
    90: "百眼阅读理解",
    100: "塞纳河畔的春水",
}

FINAL_BOSS_ALIAS = "期末考试"
MERCHANT_NAME = "ego"


def zone_for_floor(floor: int) -> SchoolZone:
    return SCHOOL_ZONES[min(9, max(0, (floor - 1) // 10))]


def topic_for_floor(floor: int) -> str:
    zone = zone_for_floor(floor)
    return zone.topics[(max(1, floor) - 1) % 10]


def monster_names_for_floor(floor: int) -> tuple[str, str, str]:
    """每层三只专属普通怪；主题前缀确保跨楼层不重名。"""
    zone = zone_for_floor(floor)
    topic = topic_for_floor(floor)
    return tuple(f"{topic}·{form}" for form in zone.monster_forms)


def small_boss_name_for_floor(floor: int) -> str:
    return f"{topic_for_floor(floor)}课代表"


def floor_label(floor: int) -> str:
    zone = zone_for_floor(floor)
    return f"{zone.location}·{topic_for_floor(floor)}"


def validate_school_content() -> None:
    names = [name for floor in range(1, 101) for name in monster_names_for_floor(floor)]
    if len(names) != 300 or len(set(names)) != 300:
        raise ValueError("学校地下城必须为100层提供300个不重复的普通怪物名称")
    if len(SCHOOL_ZONES) != 10 or any(len(zone.topics) != 10 for zone in SCHOOL_ZONES):
        raise ValueError("学校地下城必须包含10个区域，每区10个楼层主题")


validate_school_content()
