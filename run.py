import argparse
import json
import time
from crawler_zufe.login import IZUFE
from crawler_zufe.service import MajorService, NetService, CourseService
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
    ts_fundamental = None
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

    ts_fundamental_cos = courses.get('通识基础必修课')
    if ts_fundamental_cos and len(ts_fundamental_cos):
        ts_fundamental = dict(common)
        ts_fundamental.update({'courses': ts_fundamental_cos})
    else:
        logger.warning('未检测到通识基础必修课的配置。')
        ts_fundamental = None

    net_cos = courses.get('网络课程')
    if net_cos and len(net_cos):
        net = dict(common)
        net.update({'courses': net_cos})
    else:
        logger.warning('未检测到网络课程的配置。')
        net = None

    major_cos = courses.get('主修课程')
    if major_cos and len(major_cos):
        major = dict()
        major.update({'courses': major_cos})
    else:
        logger.warning('未检测到主修课程的配置。')
        major = None

    if not (elective or net or major):
        logger.warning('你未配置任何选课课程，请重新确认配置文件。如果你不需要选课，请忽略本条信息。')

    return common, elective, net, major, ts_fundamental


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

    common, elective, net, major, ts_fundamental = check_config(config_file)

    zufe = IZUFE(username=common.get('username'), password=common.get('password'))
    zufe.login()
    # # 启动选课服务
    if not args.only_login:

        zufe.get_chase_course_session()
        
        # 根据配置文件内各课程状态选择课程
        if elective:  # 通识选修课
            elective_service = CourseService(zufe.extract(), elective)
            elective_service.start("通识选修课")
        
        # if ts_fundamental:  # 通识基础必修课
        #     ts_fundamental_service = CourseService(zufe.extract(), ts_fundamental)
        #     ts_fundamental_service.start("通识基础必修课")
        
        # if major:  # 主修课程
        #     major_service = CourseService(zufe.extract(), major)
        #     major_service.start("主修课程")

        # if net:  # 网络课程
        #     net_service = CourseService(zufe.extract(), net)
        #     net_service.start("网络课程")

if __name__ == '__main__':
    main()