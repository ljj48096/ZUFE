import logging
import random
import time
import urllib.parse
from copy import deepcopy, copy
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image
from bs4 import BeautifulSoup
import re
from utils.train import get_clf, recognize_img
from utils.util import get_logger, send_email
import json
import datetime
logger = get_logger(__name__)

DELAY = 1  # 查询延迟时间
RETRY_TIMES = 1e3  # 重试次数


class BaseService:
    def __init__(self, zufe, kwargs):
        self.username = zufe.get('username')
        self.soup = zufe.get('soup')
        self.headers = zufe.get('headers')
        self.session = deepcopy(zufe.get('session'))  # 防止修改原session
        self.courses = kwargs.get('courses')
        # self.clf = get_clf()
        self.njdm_id =zufe.get("njdm_id")   # 年级代码
        self.zyh_id =zufe.get("zyh_id")   # 专业代码
        self.bh_id = zufe.get("bh_id")   # 班号id
        self.xqh_id = zufe.get("xqh_id")   # 校区代码
        self.jd_id = zufe.get("jd_id")   # 学院代码
        self.from_email = kwargs.get('from_email', None)
        self.from_email_psw = kwargs.get('from_email_psw', None)
        self.to_email = kwargs.get('to_email', None)
        self.url = None
        self.delay = kwargs.get('delay', DELAY)
        self.retry_times = kwargs.get('retry_times', RETRY_TIMES)
        self.courses_ok = list()

    def start(self):
        pass

    def transform_xqh_id(self):
        """转换校区代码"""
        if self.xqh_id == "下沙校区":
            return "2"
        elif self.xqh_id == "文华校区":
            return "1"
        else:
            return "0"
        
    def select_course(self):
        pass

    def get_common_form_data(self):
        """获取共同需要的form data"""
        pass

    def get_form_data(self):
        """准备form_data"""
        pass

    def update_form_data(self, page, form_data):
        try:
            VIEWSTATE = page.find('input', id='__VIEWSTATE')
            EVENTVALIDATION = page.find('input', id='__EVENTVALIDATION')

            form_data['__VIEWSTATE'] = VIEWSTATE.get('value', form_data['__VIEWSTATE']) if VIEWSTATE else form_data[
                '__VIEWSTATE']
            form_data['__EVENTVALIDATION'] = EVENTVALIDATION.get('value',
                                                                 form_data['__EVENTVALIDATION']) if EVENTVALIDATION else \
                form_data['__EVENTVALIDATION']
        except Exception as e:
            logging.exception(e)
            raise e

        return form_data

    def print_info(self):
        info = list()
        for cos in self.courses:
            info.append(cos.get('课程名称'))
        logger.info("待选课程：%s", info)

        info = list()
        for cos in self.courses_ok:
            info.append(cos.get('课程名称'))
        logger.info("已选课程：%s", info)

    def send_email(self, content):
        if self.from_email and self.from_email_psw and self.to_email:
            send_email(from_addr=self.from_email, psw=self.from_email_psw, to_addr=self.to_email, content=content)
        else:
            logger.warning('发送邮件失败，缺少相关数据。')


class GeneralService(BaseService):
    """通识选修课程的选课server"""

    def start(self):
        """启动抢课"""
        
        logger.info('开始进行通识选修课程的选课...')
        xkkz_id = "294EFF45B7F3691AE063A40810ACC46B"  # 通识选修课选课id
        click_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512"
        
        # 获取隐藏值字典
        hidden_elements_dict = {}
        soup_hidden = self.soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value 

        # 构造payload
        payload = {
            "xkkz_id": xkkz_id,
            "xszxzt": "1",
            "njdm_id": self.njdm_id,
            "zyh_id": self.zyh_id,
            "kspage": "1",
            "jspage": "1",
            "jxbzb": ""
            }
        payload.update(hidden_elements_dict)
        # print(hidden_elements_dict)
        # with open('payload.json', 'w', encoding='utf-8') as f:
        #     json.dump(payload, f, ensure_ascii=False, indent=4)
        # print(payload)
        # 发送第一次请求
        rsp = self.session.post(click_url, data=payload, headers=self.headers)

        # 解析页面
        if rsp.status_code == 200:
            soup = BeautifulSoup(rsp.text, 'lxml')
            # 找到<link>标签
            link_tag = soup.find('link', rel='stylesheet')
            # 提取 href 属性值
            href_value = link_tag.get('href', '')
            # 使用正则表达式提取 ver 参数的值
            ver_match = re.search(r'ver=(\d+)', href_value)
            if ver_match:
                ver_value = ver_match.group(1)
            else:
                logger.error('ver参数提取失败，无法继续。')
                return
        
        # 发送第二次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第三次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/jwglxt-common_zh_CN.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
 
        # 发送第四次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/N253512_zh_CN.js?ver={int(ver_value)+1}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第五次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
        
        """发送查询对应课程名称课程相关信息请求"""
        # 查询url
        course_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512"
        # 更新herders
        self.headers.update({
            "Referer": "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", 
            "Content-Length": "452", 
            "X-Requested-With": "XMLHttpRequest", 
            })
        
        # 构建新的payload
        payload = {
            "rwlx": "2",
            "xkly": "0",
            "zyh_id": payload.get("zyh_id"), 
            "zyh_id_1": payload.get("zyh_id_1"),
            "bklx_id": "0",  # 定值
            "njdm_id": payload.get("njdm_id"),  # 年级代码
            "njdm_id_1": payload.get("njdm_id_1"),
            "sfkkjyxdxnxq": "0",
            "xqh_id": payload.get("xqh_id"),  # 校区号
            "jg_id": payload.get("jg_id"),  # 学院id
            "zyfx_id": payload.get("zyfx_id"),  # 专业方向
            "bh_id": payload.get("bh_id"),  # 班号id
            "bjgkczxbbjwcx": "0",
            "xbm": payload.get("xbm"), 
            "xz": "4",  # 学制
            "ccdm": "3",
            "xsbj": "4294967296",  # 定值
            "sfkknj": "0",
            "gnjkxdnj": "0",
            "sfkkzy": "0",
            "kzybkxy": "0",
            "sfznkx": "0",
            "zdkxms": "0",
            "sfkxq": "0",
            "sfkcfx": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxqm": "12",  # 定值
            "kklxdm": "10",  # 10为选修课 01为主修课
            "bbhzxjxb": "0",
            "rlkz": "0",
            "xkzgbj": "0",
            "kspage": "1",
            "jspage": "10",
            "jxbzb": "",
            "xkxnm": "2024", 
            "filter_list[0]": "",
        }

        """查询待选课相关信息"""
        for coure_info in self.courses:
            courese_name = coure_info.get('课程名称')
            course_id = coure_info.get('课程代码', None)
            jxb_name = coure_info.get('教学班名称', None)
            
            # 更新payload
            payload.update({
                "filter_list[0]": courese_name, 
            })

            # 发送查询请求
            try: 
                temp_session = deepcopy(self.session)
                rsp = temp_session.post(course_url, data=payload, headers=self.headers)
            except Exception as e:
                logger.error(f'查询<{courese_name}>课程信息失败。')
                continue

            data = rsp.json()
            if data.get('tmpList') == []:
                logger.info(f'课程<{courese_name}>查询失败。')
                logger.info('可能是该课程不存在或者名字打错了。')
                continue
            
            # with open('课程信息查询结果.json', 'w', encoding='utf-8') as f:
            #     json.dump(data, f, ensure_ascii=False, indent=4)

            tmpList = data.get('tmpList', [])  # 同名课程相关信息
            
            for course_base_info in tmpList:
                num_limit = course_base_info["queryModel"]["limit"]  # 课程名数量限制
                num_alread_selected = course_base_info["rwzxs"]  # 已选课程数量
                # if num_limit < num_alread_selected:
                #     logger.info(f'课程<{courese_name}>已满。')
                #     continue
                # 获得选课所需的参数
                jxb_ids = course_base_info["jxb_id"]  # 选课id
                kch_id = course_base_info["kch_id"]  # 课程号
                kklxdm = course_base_info["kklxdm"]
                kcmc = course_base_info["kcmc"]  # 课程名称
                kch = course_base_info["kch"]  # 课程代码
                xf = course_base_info["xf"]  # 学分
                jxbmc = course_base_info["jxbmc"]  # 教学班名称
                # 防止选错班
                if jxb_name != None and jxbmc == jxb_name:
                    break
                if course_id != None and kch == course_id:
                    break
                
            # 构造选课用的payload
            temp_payload1 = {
                "jxb_ids": jxb_ids,
                "kch_id": kch_id,
                "njdm_id": payload.get("njdm_id"),
                "bj": "7",   # 未知
                "zyh_id": payload.get("zyh_id"), 
                "xkxnm": payload.get("xkxnm"),
                "xkxqm": payload.get("xkxqm"),
                "kklxdm": kklxdm,
            }
            # temp_payload1.pop("bj")
            temp_payload2 = temp_payload1
            temp_payload2.update({
                "kklxdm": kklxdm,
                "kcmc": f"({kch}){kcmc} - {xf} 学分",
                "rwlx": "2",
                "rlkz": "0",
                "rlzlkz": "0",
                "sxbj": "0",
                "xxkbj": "0",
                "qz": "0",
                "cxbj": "0", 
                "xkkz_id": xkkz_id,
                "xklc": "1"
                })
            
            url1 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxXkTitleMsg.html?gnmkdm=N253512"
            url2 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512"
            # 发送选课请求
            count = 0
            infnite = False
            if self.retry_times == 1:  # 挂着抢课
                infnite = True

            while count < self.retry_times or infnite:
                count += 1
                try:
                    logger.info(f'<{courese_name}>第{count}次尝试选课...')
                    rsp1 = temp_session.post(url1, data=temp_payload1, headers=self.headers)
                    with open('rsp1.html', 'w', encoding='utf-8') as f:
                        f.write(rsp.text)
                    rsp2 = temp_session.post(url2, data=temp_payload2, headers=self.headers)
                    with open('rsp2.html', 'w', encoding='utf-8') as f:
                        f.write(rsp.text)
                    if rsp2.status_code == 200 and rsp1.status_code == 200:
                        msg = rsp2.json()["flag"]
                        if msg == "1": 
                            logger.info(f'课程<{courese_name}>选课成功。')
                            break
                        else:
                            # logger.info(f'课程<{courese_name}>第{count}次没选上。即将重试')
                            time.sleep(self.delay)
                            continue
                except Exception as e:
                    logger.error(f'课程<{courese_name}>第{count}次选课失败。')
                    continue


class NetService(BaseService):
    """网络课程的选课server"""

    def start(self):
        """启动抢课"""
        
        logger.info('开始进行网络课程的选课...')
        xkkz_id = "294FB79AA98775D1E063A30810AC098D"  # 网络课选课id
        click_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512"
        
        # 获取隐藏值字典
        hidden_elements_dict = {}
        soup_hidden = self.soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value 

        # 构造payload
        payload = {
            "xkkz_id": xkkz_id,
            "xszxzt": "1",
            "njdm_id": self.njdm_id,
            "zyh_id": self.zyh_id,
            "kspage": "1",
            "jspage": "1",
            "jxbzb": ""
            }
        payload.update(hidden_elements_dict)
        # print(hidden_elements_dict)
        with open('payload.json', 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        # print(payload)
        # 发送第一次请求
        rsp = self.session.post(click_url, data=payload, headers=self.headers)

        # 解析页面
        if rsp.status_code == 200:
            soup = BeautifulSoup(rsp.text, 'lxml')
            # 找到<link>标签
            link_tag = soup.find('link', rel='stylesheet')
            # 提取 href 属性值
            href_value = link_tag.get('href', '')
            # 使用正则表达式提取 ver 参数的值
            ver_match = re.search(r'ver=(\d+)', href_value)
            if ver_match:
                ver_value = ver_match.group(1)
            else:
                logger.error('ver参数提取失败，无法继续。')
                return
        
        # 发送第二次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第三次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/jwglxt-common_zh_CN.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
 
        # 发送第四次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/N253512_zh_CN.js?ver={int(ver_value)+1}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第五次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
        
        """发送查询对应课程名称课程相关信息请求"""
        # 查询url
        course_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512"
        # 更新herders
        self.headers.update({
            "Referer": "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", 
            "Content-Length": "452", 
            "X-Requested-With": "XMLHttpRequest", 
            })
        
        # 构建新的payload
        payload = {
            "rwlx": "2",
            "xkly": "0",
            "zyh_id": payload.get("zyh_id"), 
            "zyh_id_1": payload.get("zyh_id_1"),
            "bklx_id": "0",  # 定值
            "njdm_id": payload.get("njdm_id"),  # 年级代码
            "njdm_id_1": payload.get("njdm_id_1"),
            "sfkkjyxdxnxq": "0",
            "xqh_id": payload.get("xqh_id"),  # 校区号
            "jg_id": payload.get("jg_id"),  # 学院id
            "zyfx_id": payload.get("zyfx_id"),  # 专业方向
            "bh_id": payload.get("bh_id"),  # 班号id
            "bjgkczxbbjwcx": "0",
            "xbm": payload.get("xbm"), 
            "xz": "4",  # 学制
            "ccdm": "3",
            "xsbj": "4294967296",  # 定值
            "sfkknj": "0",
            "gnjkxdnj": "0",
            "sfkkzy": "0",
            "kzybkxy": "0",
            "sfznkx": "0",
            "zdkxms": "0",
            "sfkxq": "0",
            "sfkcfx": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxqm": "12",  # 定值
            "bbhzxjxb": "0",
            "rlkz": "0",
            "xkzgbj": "0",
            "kspage": "1",
            "jspage": "10",
            "jxbzb": "",
            "xkxnm": "2024", 
            "kklxdm": "16",  # 10为选修课 01为主修课，16为网络课程
            "filter_list[0]": "",
            # "firstKklxmc": "通识/校际选修课",
            # "firstXkkzId": xkkz_id,
        }

        """查询待选课相关信息"""
        for coure_info in self.courses:
            courese_name = coure_info.get('课程名称')
            course_id = coure_info.get('课程代码', None)
            jxb_name = coure_info.get('教学班名称', None)
            
            
            # 更新payload
            payload.update({
                "filter_list[0]": courese_name, 
            })

            # 发送查询请求
            try: 
                temp_session = deepcopy(self.session)
                rsp = temp_session.post(course_url, data=payload, headers=self.headers)
            except Exception as e:
                logger.error(f'查询<{courese_name}>课程信息失败。')
                continue

            data = rsp.json()
            # with open('data.json', 'w', encoding='utf-8') as f:
            #     json.dump(data, f, ensure_ascii=False, indent=4)
            tmpList = data.get('tmpList', [])  # 同名课程相关信息
            
            for course_base_info in tmpList:
                num_limit = course_base_info["queryModel"]["limit"]  # 课程名数量限制
                num_alread_selected = course_base_info["rwzxs"]  # 已选课程数量
                # if num_limit < num_alread_selected:
                #     logger.info(f'课程<{courese_name}>已满。')
                #     continue
                # 获得选课所需的参数
                jxb_ids = course_base_info["jxb_id"]  # 选课id
                kch_id = course_base_info["kch_id"]  # 课程号
                kklxdm = course_base_info["kklxdm"]
                kcmc = course_base_info["kcmc"]  # 课程名称
                kch = course_base_info["kch"]  # 课程代码
                xf = course_base_info["xf"]  # 学分
                jxbmc = course_base_info["jxbmc"]  # 教学班名称
                # 防止选错班
                if jxb_name != None and jxbmc == jxb_name:
                    break
                if course_id != None and kch == course_id:
                    break
                
            # 构造选课用的payload
            temp_payload1 = {
                "jxb_ids": jxb_ids,
                "kch_id": kch_id,
                "njdm_id": payload.get("njdm_id"),
                "bj": "7",   # 未知
                "zyh_id": payload.get("zyh_id"), 
                "xkxnm": payload.get("xkxnm"),
                "xkxqm": payload.get("xkxqm"),
                "kklxdm": kklxdm,
            }
            # temp_payload1.pop("bj")
            temp_payload2 = temp_payload1
            temp_payload2.update({
                "kklxdm": kklxdm,
                "kcmc": f"({kch}){kcmc} - {xf} 学分",
                "rwlx": "1",
                "rlkz": "0",
                "rlzlkz": "0",
                "sxbj": "0",
                "xxkbj": "0",
                "qz": "0",
                "cxbj": "0", 
                "xkkz_id": xkkz_id,
                "xklc": "1"
                })
            
            url1 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxXkTitleMsg.html?gnmkdm=N253512"
            url2 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512"
            # 发送选课请求
            count = 0
            infnite = False
            if self.retry_times == 1:  # 挂着抢课
                infnite = True
            while count < self.retry_times or infnite:
                count += 1
                try:
                    logger.info(f'<{courese_name}>第{count}次尝试选课...')
                    rsp1 = temp_session.post(url1, data=temp_payload1, headers=self.headers)
                    # with open('rsp1.html', 'w', encoding='utf-8') as f:
                    #     f.write(rsp.text)
                    rsp2 = temp_session.post(url2, data=temp_payload2, headers=self.headers)
                    # with open('rsp2.html', 'w', encoding='utf-8') as f:
                    #     f.write(rsp.text)
                    if rsp2.status_code == 200 and rsp1.status_code == 200:
                        msg = rsp2.json()["flag"]
                        if msg == "1": 
                            logger.info(f'课程<{courese_name}>选课成功。')
                            break
                        else:
                            logger.info(f'课程<{courese_name}>第{count}次没选上。即将重试')
                            time.sleep(self.delay)
                            continue
                except Exception as e:
                    logger.error(f'课程<{courese_name}>第{count}次选课失败。')
                    continue

class MajorService(BaseService):
    """主修课程的选课server"""

    def start(self):
        """启动抢课"""
        
        logger.info('开始进行主修课程的选课...')
        xkkz_id = "294F24C520516E0EE063A30810AC2858"  # 主修课选课id
        click_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512"
        
        # 获取隐藏值字典
        hidden_elements_dict = {}
        soup_hidden = self.soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value 

        # 构造payload
        payload = {
            "xkkz_id": xkkz_id,
            "xszxzt": "1",
            "njdm_id": self.njdm_id,
            "zyh_id": self.zyh_id,
            "kspage": "1",
            "jspage": "1",
            "jxbzb": ""
            }
        payload.update(hidden_elements_dict)
        # print(hidden_elements_dict)
        with open('payload.json', 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        # print(payload)
        # 发送第一次请求
        rsp = self.session.post(click_url, data=payload, headers=self.headers)

        # 解析页面
        if rsp.status_code == 200:
            soup = BeautifulSoup(rsp.text, 'lxml')
            # 找到<link>标签
            link_tag = soup.find('link', rel='stylesheet')
            # 提取 href 属性值
            href_value = link_tag.get('href', '')
            # 使用正则表达式提取 ver 参数的值
            ver_match = re.search(r'ver=(\d+)', href_value)
            if ver_match:
                ver_value = ver_match.group(1)
            else:
                logger.error('ver参数提取失败，无法继续。')
                return
        
        # 发送第二次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第三次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/jwglxt-common_zh_CN.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
 
        # 发送第四次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/N253512_zh_CN.js?ver={int(ver_value)+1}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第五次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
        
        """发送查询对应课程名称课程相关信息请求"""
        # 查询url
        course_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512"
        # 更新herders
        self.headers.update({
            "Referer": "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", 
            "Content-Length": "452", 
            "X-Requested-With": "XMLHttpRequest", 
            })
        
        # 构建新的payload
        payload = {
            "rwlx": "2",
            "xkly": "0",
            "zyh_id": payload.get("zyh_id"), 
            "zyh_id_1": payload.get("zyh_id_1"),
            "bklx_id": "0",  # 定值
            "njdm_id": payload.get("njdm_id"),  # 年级代码
            "njdm_id_1": payload.get("njdm_id_1"),
            "sfkkjyxdxnxq": "0",
            "xqh_id": payload.get("xqh_id"),  # 校区号
            "jg_id": payload.get("jg_id"),  # 学院id
            "zyfx_id": payload.get("zyfx_id"),  # 专业方向
            "bh_id": payload.get("bh_id"),  # 班号id
            "bjgkczxbbjwcx": "0",
            "xbm": payload.get("xbm"), 
            "xz": "4",  # 学制
            "ccdm": "3",
            "xsbj": "4294967296",  # 定值
            "sfkknj": "0",
            "gnjkxdnj": "0",
            "sfkkzy": "0",
            "kzybkxy": "0",
            "sfznkx": "0",
            "zdkxms": "0",
            "sfkxq": "0",
            "sfkcfx": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxqm": "12",  # 定值
            # "kklxdm": "01",  # 10为选修课 01为主修课
            "bbhzxjxb": "0",
            "rlkz": "0",
            "xkzgbj": "0",
            "kspage": "1",
            "jspage": "10",
            "jxbzb": "",
            "xkxnm": "2024", 
            "kklxdm": "01", 
            "filter_list[0]": "",
            # "firstKklxmc": "通识/校际选修课",
            # "firstXkkzId": xkkz_id,
        }

        """查询待选课相关信息"""
        for coure_info in self.courses:
            courese_name = coure_info.get('课程名称')
            course_id = coure_info.get('课程代码', None)
            
            # 更新payload
            payload.update({
                "filter_list[0]": courese_name, 
            })

            # 发送查询请求
            try: 
                temp_session = deepcopy(self.session)
                rsp = temp_session.post(course_url, data=payload, headers=self.headers)
            except Exception as e:
                logger.error(f'查询<{courese_name}>课程信息失败。')
                continue

            data = rsp.json()
            # with open('data.json', 'w', encoding='utf-8') as f:
            #     json.dump(data, f, ensure_ascii=False, indent=4)
            tmpList = data.get('tmpList', [])  # 同名课程相关信息
            
            for course_base_info in tmpList:
                num_limit = course_base_info["queryModel"]["limit"]  # 课程名数量限制
                num_alread_selected = course_base_info["rwzxs"]  # 已选课程数量
                # if num_limit < num_alread_selected:
                #     logger.info(f'课程<{courese_name}>已满。')
                #     continue
                # 获得选课所需的参数
                jxb_ids = course_base_info["jxb_id"]  # 选课id
                kch_id = course_base_info["kch_id"]  # 课程号
                kklxdm = course_base_info["kklxdm"]
                kcmc = course_base_info["kcmc"]  # 课程名称
                kch = course_base_info["kch"]  # 课程代码
                xf = course_base_info["xf"]  # 学分
                # 防止名称相同但代码不同导致的选课
                if kch == course_id:
                    break
                
            # 构造选课用的payload
            temp_payload1 = {
                "jxb_ids": jxb_ids,
                "kch_id": kch_id,
                "njdm_id": payload.get("njdm_id"),
                "bj": "7",   # 未知
                "zyh_id": payload.get("zyh_id"), 
                "xkxnm": payload.get("xkxnm"),
                "xkxqm": payload.get("xkxqm"),
                "kklxdm": kklxdm,
            }
            # temp_payload1.pop("bj")
            temp_payload2 = temp_payload1
            temp_payload2.update({
                "kklxdm": kklxdm,
                "kcmc": f"({kch}){kcmc} - {xf} 学分",
                "rwlx": "1",
                "rlkz": "0",
                "rlzlkz": "0",
                "sxbj": "0",
                "xxkbj": "0",
                "qz": "0",
                "cxbj": "0", 
                "xkkz_id": xkkz_id,
                "xklc": "1"
                })
            
            url1 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxXkTitleMsg.html?gnmkdm=N253512"
            url2 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512"
            # 发送选课请求
            count = 0
            infnite = False
            if self.retry_times == 1:  # 挂着抢课
                infnite = True
            while count < self.retry_times or infnite:
                count += 1
                try:
                    logger.info(f'<{courese_name}>第{count}次尝试选课...')
                    rsp1 = temp_session.post(url1, data=temp_payload1, headers=self.headers)
                    # with open('rsp1.html', 'w', encoding='utf-8') as f:
                    #     f.write(rsp.text)
                    rsp2 = temp_session.post(url2, data=temp_payload2, headers=self.headers)
                    # with open('rsp2.html', 'w', encoding='utf-8') as f:
                    #     f.write(rsp.text)
                    if rsp2.status_code == 200 and rsp1.status_code == 200:
                        msg = rsp2.json()["flag"]
                        if msg == "1": 
                            logger.info(f'课程<{courese_name}>选课成功。')
                            break
                        else:
                            logger.info(f'课程<{courese_name}>第{count}次没选上。即将重试')
                            time.sleep(self.delay)
                            continue
                except Exception as e:
                    logger.error(f'课程<{courese_name}>第{count}次选课失败。')
                    continue

class CourseService(BaseService):
    """课程的选课server"""

    def start(self, course_type):
        """启动抢课"""
        if course_type == "主修课程":
            xkkz_id = "294F24C520516E0EE063A30810AC2858"
            kklxdm = "01"
        elif course_type == "通识选修课":
            xkkz_id = "294EFF45B7FF691AE063A40810ACC46B"
            kklxdm = "10"
        elif course_type == "网络课程":
            xkkz_id = "294FB79AA98775D1E063A30810AC098D"
            kklxdm = "16"
        else:
            logger.error(f'课程类型<{course_type}>不存在。')
            return None

        logger.info(f'开始进行{course_type}的选课...')
        click_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512"
        
        # 获取隐藏值字典
        hidden_elements_dict = {}
        soup_hidden = self.soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value 

        # 构造payload
        payload = {
            "xkkz_id": xkkz_id,
            "xszxzt": "1",
            "njdm_id": self.njdm_id,
            "zyh_id": self.zyh_id,
            "kspage": "1",
            "jspage": "1",
            "jxbzb": ""
            }
        payload.update(hidden_elements_dict)
        # print(hidden_elements_dict)
        # with open('payload.json', 'w', encoding='utf-8') as f:
        #     json.dump(payload, f, ensure_ascii=False, indent=4)
        # print(payload)
        # 发送第一次请求
        rsp = self.session.post(click_url, data=payload, headers=self.headers)

        # 解析页面
        if rsp.status_code == 200:
            soup = BeautifulSoup(rsp.text, 'lxml')
            # 找到<link>标签
            link_tag = soup.find('link', rel='stylesheet')
            # 提取 href 属性值
            href_value = link_tag.get('href', '')
            # 使用正则表达式提取 ver 参数的值
            ver_match = re.search(r'ver=(\d+)', href_value)
            if ver_match:
                ver_value = ver_match.group(1)
            else:
                logger.error('ver参数提取失败，无法继续。')
                return
        
        # 发送第二次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第三次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/jwglxt-common_zh_CN.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
 
        # 发送第四次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/globalweb/comp/i18n/N253512_zh_CN.js?ver={int(ver_value)+1}"
        rsp = self.session.get(click_url, headers=self.headers)

        # 发送第五次请求
        click_url = f"http://jwxt.zufe.edu.cn/jwglxt/js/comp/jwglxt/xkgl/xsxk/zzxkYzbZy.js?ver={ver_value}"
        rsp = self.session.get(click_url, headers=self.headers)
        
        """发送查询对应课程名称课程相关信息请求"""
        # 查询url
        course_url = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512"
        # 更新herders
        self.headers.update({
            "Referer": "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", 
            "Content-Length": "452", 
            "X-Requested-With": "XMLHttpRequest", 
            })
        
        # 构建新的payload
        payload = {
            "rwlx": "2",
            "xkly": "0",
            "zyh_id": payload.get("zyh_id"), 
            "zyh_id_1": payload.get("zyh_id_1"),
            "bklx_id": "0",  # 定值
            "njdm_id": payload.get("njdm_id"),  # 年级代码
            "njdm_id_1": payload.get("njdm_id_1"),
            "sfkkjyxdxnxq": "0",
            "xqh_id": payload.get("xqh_id"),  # 校区号
            "jg_id": payload.get("jg_id"),  # 学院id
            "zyfx_id": payload.get("zyfx_id"),  # 专业方向
            "bh_id": payload.get("bh_id"),  # 班号id
            "bjgkczxbbjwcx": "0",
            "xbm": payload.get("xbm"), 
            "xz": "4",  # 学制
            "ccdm": "3",
            "xsbj": "4294967296",  # 定值
            "sfkknj": "0",
            "gnjkxdnj": "0",
            "sfkkzy": "0",
            "kzybkxy": "0",
            "sfznkx": "0",
            "zdkxms": "0",
            "sfkxq": "0",
            "sfkcfx": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxqm": "12",  # 定值
            "bbhzxjxb": "0",
            "rlkz": "0",
            "xkzgbj": "0",
            "kspage": "1",
            "jspage": "10",
            "jxbzb": "",
            "xkxnm": str(datetime.datetime.now().year), 
            "kklxdm": kklxdm, 
            "filter_list[0]": "",
        }

        url1 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxXkTitleMsg.html?gnmkdm=N253512"
        url2 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512"
        # 发送选课请求
        count = 0
        infnite = False
        if self.retry_times == 1:  # 挂着抢课
            infnite = True

        while count < self.retry_times or infnite:
            count += 1 # 记录运行次数
            # time.sleep(random.randint(1, 3)) # 延迟
            """查询待选课相关信息"""
            for _, coure_info in enumerate(self.courses):
                courese_name = coure_info.get('课程名称')
                course_id = coure_info.get('课程代码', None)
                jxb_name = coure_info.get('教学班名称', None)

                # 选上的课不再选了
                if courese_name in self.courses_ok:
                    continue
                
                # 课选完了就退出
                if len(self.courses_ok) == len(self.courses):
                    print("#"*20)
                    logger.info(f'{course_type}课程选课完毕。')
                    print("#"*20)
                    return None

                # 更新payload
                payload.update({
                    "filter_list[0]": courese_name, 
                })

                # 发送查询请求
                try: 
                    temp_session = deepcopy(self.session)
                    rsp = temp_session.post(course_url, data=payload, headers=self.headers)
                except Exception as e:
                    logger.error(f'查询<{courese_name}>课程信息失败。')
                    continue

                data = rsp.json()
                # with open('data.json', 'w', encoding='utf-8') as f:
                #     json.dump(data, f, ensure_ascii=False, indent=4)
                tmpList = data.get('tmpList', [])  # 同名课程相关信息
                jxb_ids = None
                kch_id = None
                kklxdm = None
                kcmc = None
                kch = None
                xf = None
                jxbmc = None
                num_limit = None
                num_alread_selected = None

                for course_base_info in tmpList:
                    # num_limit = course_base_info["queryModel"]["limit"]  # 课程名数量限制
                    num_alread_selected = course_base_info["yxzrs"]  # 已选课程数量
                    # 获得选课所需的参数
                    jxb_ids = course_base_info["jxb_id"]  # 选课id
                    kch_id = course_base_info["kch_id"]  # 课程号
                    kklxdm = course_base_info["kklxdm"]
                    kcmc = course_base_info["kcmc"]  # 课程名称

                    kch = course_base_info["kch"]  # 课程代码
                    xf = course_base_info["xf"]  # 学分
                    jxbmc = course_base_info["jxbmc"]  # 教学班名称
                    # 防止选错班
                    if jxb_name:
                        if jxbmc == jxb_name:
                            break
                        else:
                            continue
                    
                    if course_id:
                        if course_id != None and kch == course_id:
                            break
                        else:
                            continue
                    
                # 课程已满, 跳过
                # if int(num_alread_selected) % 5 == 0:
                #     logger.info(f'课程<{courese_name}>教学班{jxbmc}当前选课人数已满。')
                #     next    

                # 构造选课用的payload
                temp_payload1 = {
                    "jxb_ids": jxb_ids,
                    "kch_id": kch_id,
                    "njdm_id": payload.get("njdm_id"),
                    "bj": "7",   # 未知
                    "zyh_id": payload.get("zyh_id"), 
                    "xkxnm": payload.get("xkxnm"),
                    "xkxqm": payload.get("xkxqm"),
                    "kklxdm": kklxdm,
                }

                temp_payload2 = {
                    "jxb_ids": jxb_ids,
                    "kch_id": kch_id,
                    "kcmc": f"({kch}){kcmc} - {xf} 学分",
                    "rwlx": "2",
                    "rlkz": "0",
                    "rlzlkz": "1",
                    "sxbj": "1",
                    "xxkbj": "0",
                    "qz": "0",
                    "cxbj": "0", 
                    "xkkz_id": xkkz_id,
                    "njdm_id": payload.get("njdm_id"),
                    "zyh_id": payload.get("zyh_id"),
                    "kklxdm": kklxdm,
                    "xklc": "2",
                    "xkxnm": payload.get("xkxnm"),
                    "xkxqm": payload.get("xkxqm"),
                    "jcxx_id":"",
                    }


                url1 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxXkTitleMsg.html?gnmkdm=N253512"
                url2 = "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512"

                # 发送选课请求
                try:
                    logger.info(f'<{courese_name}>第{count}次尝试选课...')
                    rsp1 = temp_session.post(url1, data=temp_payload1, headers=self.headers)

                    rsp2_headers = self.headers.copy()
                    rsp2_headers = {
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Accept-Encoding": "gzip, deflate",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Content-Length": "336",
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                        # "Cookie": "JSESSIONID=9BD7FDD30681CB0C942B7276666A619D; route=da8033a7a2a4367c0c7a15cb1b8ef6dd",
                        "Host": "jwxt.zufe.edu.cn",
                        "Origin": "http://jwxt.zufe.edu.cn",
                        "Pragma": "no-cache",
                        "Referer": "http://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                        "X-Requested-With": "XMLHttpRequest"
                        }

                    rsp2 = temp_session.post(url2, data=temp_payload2, headers=rsp2_headers)
                    
                    if rsp2.status_code == 200 and rsp1.status_code == 200:
                        with open('rsp1.html', 'w', encoding='utf-8') as f:
                            f.write(rsp1.text)
                        with open('rsp2.html', 'w', encoding='utf-8') as f:
                            f.write(rsp2.text)
                        msg = rsp2.json()["flag"]
                        
                        if msg == "1": 
                            logger.info(f'{course_type}课程<{kcmc}>选课成功！')
                            self.courses_ok.append(kcmc)
                            continue
                        elif msg == "-1":
                            logger.info(f'课程<{kcmc}>教学班{jxbmc}当前选课人数已满！')
                        else:
                            logger.info(f'{course_type}课程<{kcmc}>第{count}次没选上。即将重试')
                            time.sleep(self.delay)
                            continue
                except Exception as e:
                    logger.error(f'{course_type}课程<{kcmc}>第{count}次选课失败。')
                    continue