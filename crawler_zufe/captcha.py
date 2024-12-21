import requests
from bs4 import BeautifulSoup
import base64
import re
import ddddocr
import os
from PIL import Image
from utils.util import get_logger

ROOT_PATH = "captcha_data"  # 验证码数据保存路径
GIF_NAME = "captcha.gif"  # 验证码动图保存名字
CAPTCHA_PNG_SAVE_BASE_NAME = "captcha_pic"  # 验证码图片保存名字

GIF_SAVE_PATH = os.path.join(ROOT_PATH, GIF_NAME)  # 验证码动图保存路径
CAPTCHA_PNG_SAVE_PATH = os.path.join(ROOT_PATH, CAPTCHA_PNG_SAVE_BASE_NAME)  # 验证码图片保存路径

PAGE_URL = "http://jwxt.zufe.edu.cn/sso/driotlogin"  # 综合信息服务平台网址
OCR1 = ddddocr.DdddOcr()  # 实例化OCR
OCR2 = ddddocr.DdddOcr(beta=True)  # 实例化另一个OCR
OCR1.set_ranges(6)  # 设置 OCR 识别范围
OCR2.set_ranges(6)  # 小写英文a-z + 大写英文A-Z + 整数0-9
logger = get_logger(__name__)

"""解决登陆页面验证码"""
# 验证码动图保存到本地
def save_captcha_image(rsp, GIF_SAVE_PATH):
    if not os.path.exists(ROOT_PATH):
        os.makedirs(ROOT_PATH)

    try:
        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(rsp.text, 'html.parser')

        # 根据 class 查找验证码动图的 <img> 标签
        captcha_img = soup.find('img', class_='ide_code_image')

        if captcha_img and 'src' in captcha_img.attrs:
            img_src = captcha_img['src']

            # 判断图片来源是否为 base64 编码数据
            if img_src.startswith('data:image'):
                # 提取 base64 数据
                base64_data = re.sub('^data:image/.+;base64,', '', img_src)
                
                # 将 base64 数据解码为二进制数据
                img_data = base64.b64decode(base64_data)
                
                # 将图像数据保存到本地
                with open(GIF_SAVE_PATH, 'wb') as img_file:
                    img_file.write(img_data)

            else:
                # 如果不是 base64 格式，说明是正常的 URL，继续正常下载
                if not img_src.startswith("http"):
                    # 如果图片 URL 是相对路径，拼接完整的 URL
                    img_src = requests.compat.urljoin(PAGE_URL, img_src)

                img_response = requests.get(img_src)
                img_response.raise_for_status()  # 确保请求成功

                # 保存动图到本地
                with open(GIF_SAVE_PATH, 'wb') as img_file:
                    img_file.write(img_response.content)

        else:
            logger.error("未找到验证码动图！")

    except requests.exceptions.RequestException as e:
        logger.error(f"请求出现错误: {e}")

# 将验证码动图转换为 PNG 格式
def convert_gif_to_png(GIF_SAVE_PATH, png_name="captcha"):
    try:
        # 新建保存 PNG 文件夹
        if not os.path.exists(CAPTCHA_PNG_SAVE_PATH):
            os.makedirs(CAPTCHA_PNG_SAVE_PATH)
        # 打开 GIF 文件
        with Image.open(GIF_SAVE_PATH) as img:
            # 检查 GIF 是否有多个帧
            if img.is_animated:
                # 将每一帧保存为单独的 PNG 文件
                for frame_index in range(img.n_frames):
                    img.seek(frame_index)  # 移动到指定帧
                    frame = img.convert("RGBA")  # 转换为 RGBA 格式
                    temp_path = os.path.join(CAPTCHA_PNG_SAVE_PATH, f"{png_name}_{frame_index}.png")
                    frame.save(temp_path, "PNG")  # 保存为 PNG

            else:
                # 如果是单帧 GIF，直接保存为 PNG
                temp_path = os.path.join(CAPTCHA_PNG_SAVE_PATH, f"{png_name}.png")
                img.convert("RGBA").save(temp_path, "PNG")

    except Exception as e:
        logger.error(f"转换时发生错误: {e}")

# 获取验证码
def get_captcha_code(CAPTCHA_PNG_SAVE_PATH, ocr1=OCR1, ocr2=OCR2):
    png_labels = os.listdir(CAPTCHA_PNG_SAVE_PATH)  # 获取 PNG 文件名列表

    if len(png_labels) == 0:
        print("未找到验证码图片！")
    
    # 读取验证码图片
    for png_label in png_labels:
        temp_path = os.path.join(CAPTCHA_PNG_SAVE_PATH, png_label)
        image = open(temp_path, "rb").read()
        result1 = ocr1.classification(image)
        result2 = ocr2.classification(image)

        if len(result1.replace(" ", "")) == 4:  # 识别结果长度为 4 则为验证码
            logger.info(f"验证码为: {result1}")
            return result1
        elif len(result2.replace(" ", "")) == 4:  # 识别结果长度为 4 则为验证码
            logger.info(f"验证码为: {result2}")
            return result2
    