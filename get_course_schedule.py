import argparse
import json
import time
from crawler_zufe.login import IZUFE
from utils.util import get_logger
from crawler_zufe.captcha import *

logger = get_logger(__name__)
CONFIG_FILE = 'config.json'
DEV_FILE = 'test.json'


def check_config(file_path):
    """
    检查配置文件，若有问题给出提示，否则返回每种选课的必要数据。
    :param file_path: 配置文件路径
    :return:
    """
    elective = None
    net = None
    major = None
    config = None
    try:
        with open(file_path, 'r', encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        logger.error('没有找到配置文件，或者配置有误，请先配置好再重试。更多可以查看 Json 文件格式。', exc_info=1)
        exit(1)
    common = dict()
    # TODO: 检查每一项，给出提示
    common['username'] = config.get('username')
    common['password'] = config.get('password')
    common['from_email'] = config.get('from_email')
    common['from_email_psw'] = config.get('from_email_psw')
    common['to_email'] = config.get('to_email')
    common['delay'] = config.get('delay')
    common["njdm_id"] = config.get("njdm_id")  # 年级代码
    common["zyh_id"] = config.get("zyh_id")  # 专业代码

    courses = config.get('courses')

    elec_cos = courses.get('通识选修课')
    if elec_cos and len(elec_cos):
        elective = dict(common)
        elective.update({'courses': elec_cos})
    else:
        logger.warning('未检测到通识选修课的配置。')
        elective = None

    net_cos = courses.get('体育课')
    if net_cos and len(net_cos):
        net = dict(common)
        net.update({'courses': net_cos})
    else:
        logger.warning('未检测到体育课的配置。')
        net = None

    major_cos = courses.get('主修课程')
    if major_cos and len(major_cos):
        major = dict()
        major.update({'courses': major_cos})
    else:
        logger.warning('未检测到普通理论课的配置。')
        major = None

    if not (elective or net or major):
        logger.warning('你未配置任何选课课程，请重新确认配置文件。如果你不需要选课，请忽略本条信息。')

    return common, elective, net, major


def parse_args():
    parser = argparse.ArgumentParser(usage='%(prog)s [options]', description='For ZUFE.', add_help=True)
    parser.add_argument('-f', '--file', dest='file', help='use special config file', metavar='FILE')
    parser.add_argument('-d', '--dev', action='store_true', dest='dev', help='run with dev mood')
    parser.add_argument('--only-login', action='store_true', dest='only_login', help='only login')
    parser.add_argument('--not-choose', action='store_true', dest='not_choose', help='do not choose course')

    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    config_file = CONFIG_FILE
    if args.file:
        config_file = args.file
    elif args.dev:
        config_file = DEV_FILE
        logger.warning('当前使用测试配置！')

    common, _, _, _ = check_config(config_file)

    zufe = IZUFE(username=common.get('username'), password=common.get('password'))
    zufe.login()

    xnm = "2024"  # 学年
    xqm = "2"  # 学期
    xqh = "下沙校区"  # 校区
    bh_id = "22207302"  # 班号

    zufe.get_schedule(xnm=xnm, xqm=xqm, xqh=xqh, bh_id=bh_id) 

if __name__ == '__main__':
    main()
