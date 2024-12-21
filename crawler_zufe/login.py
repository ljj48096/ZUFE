import json
import os
import random
import re
import requests
from bs4 import BeautifulSoup
from utils.util import get_logger, strenc
from crawler_zufe.captcha import *
import time
import pandas as pd
from crawler_zufe.service import *

logger = get_logger(__name__)

# 综合信息服务平台网址
COMPREHENSIVE_SERVICE_URL = "http://jwxt.zufe.edu.cn/sso/driotlogin"
# 保存 cookie 的文件
COOKIES_FILE = 'cookies.txt'
# 登录重试次数
RETRY = 3
# 代理池--示例
PROXY_POOL = [
"http://proxy1.com:8080", 
"http://proxy2.com:8080",
"http://proxy3.com:8080",
]
class IZUFE:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.realname = None
        self.session = requests.session()

        # 用于在各个方法里传递参数
        self.rsp = None
        self.headers = None
        self.in_url = None
        self._session = None
        self.soup = None

    def login(self):
        retry = 0
        while retry < RETRY:
            self.session = requests.session()  # 每次迭代刷新 session
            retry += 1
            logger.info('尝试第 %s 次登录', retry)
            # 只使用一次：从本地文件读取cookie
            if retry == 1 and os.path.exists(COOKIES_FILE):
                logger.info('从本地文件读取 cookies')
                with open(COOKIES_FILE, 'r') as f:
                    self.session.cookies.update(json.loads(f.read()))
            else:
                if not self._do_login():
                    logger.error(f"第{retry}次登录失败！")
                    print('可能是用户名或密码错误或梯子没关')
                    continue
                else:
                    return

            # 更新使用于选课系统的 headers
            # headers = {
            #     'Accept': '*/*',
            #     'Accept-Encoding': 'gzip, deflate, br, zstd',
            #     'Accept-Language': 'zh-CN,zh;q=0.9',
            #     'Cache-Control': 'no-cache',
            #     'Connection': 'keep-alive',
            #     'Host': 'jwxt.zufe.edu.cn',
            #     'Pragma': 'no-cache',
            #     'Referer': 'https://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default',
            #     'Sec-Fetch-Dest': 'script',
            #     'Sec-Fetch-Mode': 'no-cors',
            #     'Sec-Fetch-Site': 'same-origin',
            #     'sec-ch-ua-mobile': '?0'
            # }
            # self.session.headers.update(headers)  # 更新 headers


    def _do_login(self):
        """
        登录信息服务平台，然后转跳自主选课。
        :param: None
        
        :return: None
        """

        headers = {
            'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            'accept-encoding': "gzip, deflate, br, zstd",
            'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5",
            'cache-control': "no-cache",
            'connection': "keep-alive",
            'content-type': "application/x-www-form-urlencoded",
            'host': "jwxt.zufe.edu.cn",  # 当前请求的主机地址（登录系统的域名）。
            'origin': "http://jwxt.zufe.edu.cn/sso/driotlogin",  # 综合服务信息平台网址
            'upgrade-insecure-requests': "1",
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36',
        }
        
        payload = self._get_payload(COMPREHENSIVE_SERVICE_URL)  # 获取所需登录参数
        # print("成功获取到登录参数！：",payload)

        # 通过信息服务平台认证
        try:
            
            logger.info("Hit %s", COMPREHENSIVE_SERVICE_URL)
            rsp = self.session.post(COMPREHENSIVE_SERVICE_URL,
                                    data=payload,
                                    headers=headers,
                                    allow_redirects=False,
                                    timeout=5)
                 
        except requests.exceptions.Timeout:
            logger.error("请求超时")
        except requests.exceptions.RequestException as e:
            logger.error(f"请求出错: {e}")

        try:
            # 得到最终信息服务平台地址(可能存在重定向)
            while rsp.status_code == 302:
                headers.update({'origin': "https://cas.zufe.edu.cn",
                                'host': "cas.zufe.edu.cn"})  # 更新 headers
                # 获取 Location 头部
                in_url = rsp.headers.get('Location')  # 登录成功后,重定向到信息服务平台内的地址

                if "verify" in in_url:  # 验证码
                    break
                rsp = self.session.post(in_url,
                                        data=payload,
                                        headers=headers,
                                        allow_redirects=False
                                        )

            # 进入信息服务平台
            headers.update({'Host': "jwxt.zufe.edu.cn",
                            'origin': "https://jwxt.zufe.edu.cn"})  # 更新 headers

            rsp = self.session.get(in_url, headers=headers)
            
            # 检查请求是否成功
            if rsp.status_code != 200:
                logger.error(f'进入信息服务平台失败！状态码：{rsp.status_code}')
                return False
            
            logger.info("成功进入信息服务平台！")

            self.rsp = rsp
            self.headers = headers
            self.in_url = in_url

            return True
        
        except Exception as e:
            logger.error("进入信息服务平台失败！")
            logger.error(f"错误信息：{e}")
            return
        
    def get_grade(self, xnm="", xqm="", kcbj="", file_path=None):
        """
        进入成绩查询界面，获取成绩信息，并以excel表格形式返回
        :param xnm: 学年
        :param xqm: 学期
        :param kcbj: 课程类别
        :param file_path: 保存成绩信息的excel文件路径

        :return: 成绩信息的excel表格
        """
        gnmkdm = 'N305005'  # 成绩查询功能代码
        func_name = "学生成绩查询"

        _, second_response, _session, _headers = self._base_post(gnmkdm, func_name)
        
        """解析成绩查询页面内容"""
        try:
            # 解析成绩查询页面内容
            soup = BeautifulSoup(second_response.text, 'lxml')

        except Exception as e:
            logger.error(f'解析成绩查询页面内容失败！错误: {e}')
            return None
        
        # 查找该页面隐藏元素，并构建input隐藏元素字典
        hidden_elements_dict = {}
        soup_hidden = soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value
        
        # 查询成绩URL
        grade_check_url = 'http://jwxt.zufe.edu.cn/jwglxt/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005'
        # 转换xqm
        xq_map = {"1": "3", "2": "12", "3": "16", "": ""}
        xqm_convert = xq_map[xqm]
        # 转换kcbj
        kcbj_map = {"": "", "主修": "0", "辅修": "1", "通识": "2",
                     "二专业": "3", "二学位": "4", "非学位": "5", "二学位转一专": "6"}
        kcbj_convert = kcbj_map[kcbj]
        payload = {
            "xnm": xnm,                            # 学年，例如2023
            "xqm": xqm_convert,                    # 学期，例如1表示第一学期
            "kcbj": kcbj_convert,                  # 课程标记，空表示全部
            "_search": "false",
            "nd": str(int(time.time() * 1000)),    # 时间戳，通常用于防止缓存
            "queryModel.showCount": "2000",        # 每页显示的结果数
            "queryModel.currentPage": "1",         # 当前页码
            "queryModel.sortName": "",             # 排序字段，空表示默认
            "queryModel.sortOrder": "asc",         # 排序顺序，默认升序
            # "time": "10"
            }
        try:
            grade_rsp = _session.post(grade_check_url,
                                    headers=_headers,
                                    data=payload,
                                    # cookies=cookies,
                                    )
        except Exception as e:
            logger.error(f'发送查询请求页面请求失败！错误: {e}')
            return
        
        if grade_rsp.status_code != 200:
            logger.error(f"成绩查询页面请求失败，状态码：{grade_rsp.status_code}")
            return

        data = json.loads(grade_rsp.text)  # 将返回的字典转换为 JSON 格式

        """如果想加查询的数据，可以把以下代码注释撇掉。得到新的json文件，再在里面找想要的的键值对"""
        # with open('grade_check_response.json', 'w', encoding='utf-8') as f:
        #     json.dump(data, f, ensure_ascii=False, indent=4)

        course_data = data.get("items")
        info_labels= [("bfzcj", "成绩"),
                      ("kcmc", "课程名称"),
                      ("bj", "班级"),
                      ("jxbmc", "教学班名称"),
                      ("kcbj", "课程标记"),
                      ("cjsfzf", "成绩是否作废"),
                      ("tjrxm", "教师名称"),
                      ("kcxzmc", "课程性质名称"),
                      ("sskcmc", "所属课程名称"),
                      ("xf", "学分"),
                      ("xfjd", "学分绩点"),
                      ("xnmmc", "学年名称"),
                      ("xqmmc", "学期"),]
        
        df_dict = {i[0]:[] for i in info_labels}  # 用于存储成绩信息的字典
        
        for course in course_data:
            for info_label in info_labels:
                df_dict[info_label[0]].append(course.get(info_label[0]))

        df = pd.DataFrame(df_dict)
        df.columns = [colname[1] for colname in info_labels]

        if file_path:
            df_name = file_path
        else:
            if xqm != "" and xnm != "":
                df_name = f"{xnm}-{int(xnm)+1}第{xqm}学期成绩.xlsx"
            elif xqm == "" and xnm != "":
                df_name = f"{xnm}-{int(xnm)+1}全部学期成绩.xlsx"
            elif xqm != "" and xnm == "":
                df_name = f"全部学年第{xqm}学期成绩.xlsx"
            else:
                df_name = "全部成绩.xlsx"

        if self.realname != None:
            df.to_excel(self.realname + df_name, index=False)
            logger.info(f"成功保存成绩信息到{self.realname + df_name}！")
        else:
            df.to_excel(df_name, index=False)
            logger.info(f"成功保存成绩信息到{df_name}！")

        return

    def get_chase_course_session(self):
        """
        用于开始抢课
        :param None
        :return: None
        """

        gnmkdm = 'N253512'  # 自主选课功能代码
        func_name = "自主选课"

        try:
            second_url, second_response, _session, _headers = self._base_post(gnmkdm, func_name)
        except Exception as e:
            return

        """
        成功进入页面后, 查看当前是否为选课阶段
        如果非选课阶段，则刷新页面，直到进入选课阶段
        """
        while True:
            second_response = _session.get(second_url, headers=_headers)
            if second_response.status_code == 200:
                soup = BeautifulSoup(second_response.text, 'html.parser')
                error_span = soup.find('span', text="对不起，当前不属于选课阶段，如有需要，请与管理员联系！")
                if error_span:
                    # 打印该元素的字符串表示
                    logger.info("当前不属于选课阶段")
                    time.sleep(0.5)  # 等待 0.5 秒后刷新页面
                else:
                    logger.info("选课开始")
                    self.soup = soup
                    break
            else:
                logger.error(f"当前会话已过期，请重新登陆")
                return None
        
        self._session = _session
        self.headers = _headers
        return
    
    def get_schedule(self, xnm="2024", xqm="2", xqh="下沙校区", bh_id="22207302"):
        """
        查询当前推荐课表出了没
        :param xnm: 学年
        :param xqm: 学期
        :param xqh: 校区
        :param bh_id: 班号
        :return: None
        """

        gnmkdm = 'N214505'  # 成绩查询功能代码
        func_name = "班级推荐课表打印"
        
        _, second_response, _session, _headers = self._base_post(gnmkdm, func_name)
        
        """解析成绩查询页面内容"""
        try:
            # 解析成绩查询页面内容
            soup = BeautifulSoup(second_response.text, 'lxml')

        except Exception as e:
            logger.error(f'解析成绩查询页面内容失败！错误: {e}')
            return None
        
        # 查找该页面隐藏元素，并构建input隐藏元素字典
        hidden_elements_dict = {}
        soup_hidden = soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value
        
        # 查询URL
        grade_check_url = f'http://jwxt.zufe.edu.cn/jwglxt/kbdy/bjkbdy_cxBjkbdyTjkbList.html?gnmkdm=N214505'
        # 转换xqm
        xq_map = {"1": "3", "2": "12", "3": "16", "": ""}
        xqm_convert = xq_map[xqm]
        # 校区号
        xqh_map = {"文华校区":"1", "下沙校区":"2", "全部":""}
        xqh_id = xqh_map[xqh]

        payload = {
            "xnm": xnm,                            # 学年，例如2023
            "xqm": xqm_convert,                    # 学期，例如1表示第一学期
            "xqh_id": xqh_id,                      # 校区号
            "bh_id": bh_id,                        # 班号
            "_search": "false",
            "nd": str(int(time.time() * 1000)),    # 时间戳，通常用于防止缓存
            "queryModel.showCount": "2000",        # 每页显示的结果数
            "queryModel.currentPage": "1",         # 当前页码
            "queryModel.sortName": "",             # 排序字段，空表示默认
            "queryModel.sortOrder": "asc",         # 排序顺序，默认升序
            "time": "10"
            }

        _headers.update({"user-agent":"'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36'"})

        while True:
            try:
                rsp = _session.post(grade_check_url,
                                        headers=_headers,
                                        data=payload,)

            except Exception as e:
                logger.error(f'发送查询请求页面请求失败！错误: {e}')
                return
            
            if rsp.status_code != 200:
                logger.error(f"成绩查询页面请求失败，状态码：{rsp.status_code}")
                return

            # 解析页面内容
            if json.loads(rsp.text)["totalResult"] < 1:
                # 打印该元素的字符串表示
                logger.info("课表未出")
                time.sleep(random.randint(3, 8))
            else:
                logger.info("课表已出")
                break

        return
      
    def _get_payload(self, url):
        rsp = self.session.get(url)  # 使用会话发送 GET 请求，获取指定 URL 的响应
        if rsp.status_code != 200:  # 检查响应状态码是否为 200（成功）
            return None

        # 使用 BeautifulSoup 解析返回的 HTML 文本，查找 id 为 'password_template' 的 script 标签
        soup = BeautifulSoup(rsp.text, 'lxml').find_all('input', {"type":"hidden"})
        # 解析 script 标签内容，再次通过 BeautifulSoup 解析
        # 遍历并打印每个隐藏元素的 id 和 value
        hidden_elements_dict = {}
        for input_element in soup:
            input_id = input_element.get('name')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value
        # print("隐藏元素字典:", hidden_elements_dict)
        
        # 通过调用 strenc 方法加密组合字符串 (用户名 + 密码 + lt)，生成 'rsa' 字段
        rsa = strenc(self.username + self.password + hidden_elements_dict["lt"], '1', '2', '3')

        # 构建表单提交所需的 payload
        payload = {
            'rsa': rsa,  # 加密的认证信息
            'ul': len(self.username),  # 用户名的长度
            'pl': len(self.password),  # 密码的长度
            'lt': hidden_elements_dict["lt"],  # 隐藏字段 'lt'
            'execution': hidden_elements_dict["execution"],  # 隐藏字段 'execution'
            '_eventId': hidden_elements_dict["_eventId"],  # 隐藏字段 '_eventId'
            "un": self.username,  # 用户名
            "pd": self.password,  # 密码
        }

        # 验证码识别
        save_captcha_image(rsp, GIF_SAVE_PATH)
        convert_gif_to_png(GIF_SAVE_PATH)
        captcha_code = get_captcha_code(CAPTCHA_PNG_SAVE_PATH)

        # 如果需要验证码，添加到 payload 中
        if captcha_code:
            payload['code'] = captcha_code

        return payload  # 返回构建好的 payload，用于后续的 POST 请求

    def _base_post(self, gnmkdm, func_name):
        _session = self.session
        _headers = self.headers
        _in_url = self.in_url

        try:
            # 解析综合信息服务平台页面内容
            soup = BeautifulSoup(self.rsp.text, 'lxml')

        except Exception as e:
            logger.error(f'解析综合信息服务平台页面内容失败！错误: {e}')
            return None
        
        # 查找该页面隐藏元素，并构建input隐藏元素字典
        hidden_elements_dict = {}
        soup_hidden = soup.find_all('input', {"type":"hidden"})
        for input_element in soup_hidden:
            input_id = input_element.get('id')
            input_value = input_element.get('value', '')  # 如果没有 value，默认为空字符串
            hidden_elements_dict[input_id] = input_value

        # 手动添加表单中的其他必要字段，比如 gnmkdm 和 sessionUserKey
        hidden_elements_dict['gnmkdm'] = gnmkdm  # 模拟点击的功能代码
        hidden_elements_dict['sessionUserKey'] = soup.find('input', {'id': 'sessionUserKey'})['value']
        # print("hidden_elements_dict:", hidden_elements_dict)
    
        """点击按钮，进入页面"""
        # 查看按钮是否存在
        course_button = soup.find('a', string=f'{func_name}')

        if not course_button:
            logger.error(f"未找到'{func_name}'的按钮！")
            return None
        
        try:
            # 发送模拟按钮点击的请求
            _headers.update({'Host': "jwxt.zufe.edu.cn",
                            "Origin":"http://jwxt.zufe.edu.cn",
                            "Accept-Encoding": "gzip, deflate",
                            "Referer": _in_url})  # 更新 headers
            payload_botton = {
                'gnmkdm': gnmkdm,  # 按钮中传递的参数
                'layout': 'default'    # 按钮中传递的参数
            }
            payload_botton.update(hidden_elements_dict)  # 合并隐藏元素字典
            # print("#############\n","payload_botton", payload_botton)
            _headers.update({
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Origin': 'https://jwxt.zufe.edu.cn',
                'Pragma': 'no-cache',
                'Referer': f'http://jwxt.zufe.edu.cn/jwglxt/xtgl/index_initMenu.html?jsdm=&_t={str(int(time.time() * 1000))}',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest',
                'sec-ch-ua-mobile': '?0',
            })

            url = 'http://jwxt.zufe.edu.cn/jwglxt/xtgl/index_cxBczjsygnmk.html?gnmkdm=index'  # 请求按钮点击的 URL
            rsp_button = _session.post(url, headers=_headers, data=payload_botton, timeout=10)
            if rsp_button.status_code == 200:
                # 保存按钮点击后的 HTML 内容
                # with open('button_click_response.html', 'w', encoding='utf-8') as file:
                #     file.write(rsp_button.text)  # 将响应的 HTML 内容写入文件
                logger.info("成功触发{}按钮！".format(func_name))
                # 第二次请求-进入界面
                second_url = f'https://jwxt.zufe.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm={gnmkdm}&layout=default'
                second_response = _session.get(second_url, headers=_headers)
                if second_response.status_code == 200:
                    logger.info(f"成功进入{func_name}页面！")
                    return second_url, second_response, _session, _headers

            else:
                print(f"页面请求失败，状态码：{rsp_button.status_code}")
                return
        except Exception as e:
            logger.error(f'按钮触发请求失败！错误: {e}')
            return
        
    def is_valid_url(self, url):
        reg = r'^http[s]*://.+$'
        return re.match(reg, url)

    def extract(self):
        zufe = {
            'session': self._session,
            "soup": self.soup,
            "headers": self.headers,
        }
        return zufe
