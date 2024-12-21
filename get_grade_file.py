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
    common['from_email'] = config.get('from_email', None)
    common['from_email_psw'] = config.get('from_email_psw', None)
    common['to_email'] = config.get('to_email', None)
    common['delay'] = config.get('delay', None)
    common["njdm_id"] = config.get("njdm_id", None)  # 年级代码
    common["zyh_id"] = config.get("zyh_id", None)  # 专业代码
    return common


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

    common = check_config(config_file)

    xnm = "2023"  # 学年，例如2023表示2023-2024年，空代表全部
    xqm = ""  # 学期，例如1表示第一学期，2表示第二学期，空代表全部
    kcbj = ""  # 课程标记，主修、辅修、二学位啥啥啥的，空代表全部

    zufe = IZUFE(username=common.get('username'), password=common.get('password'))
    zufe.login()

    zufe.get_grade(xnm, xqm, kcbj)  # 获取成绩excel文件


if __name__ == '__main__':
    main()
