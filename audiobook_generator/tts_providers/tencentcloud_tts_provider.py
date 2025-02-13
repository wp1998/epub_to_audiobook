import logging
import math
import json
import os
# from datetime import datetime, timedelta
from time import sleep
import requests

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.tts.v20190823 import tts_client, models

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.utils import split_text, set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 5  # Max_retries constant for network errors

class tencentcloudProvider(BaseTTSProvider):
    
    def __init__(self, config: GeneralConfig):
        
        config.output_format = config.output_format or "audio-16k-mp3"
        # 16$ per 1 million characters
        # or 0.016$ per 1000 characters
        self.price = 0.32
        
        secret_id = os.environ.get("TC_SECRET_ID")
        secret_key = os.environ.get("TC_SECRET_KEY")
        region = ""
        # 实例化一个认证对象，入参需要传入腾讯云账户 SecretId 和 SecretKey
        cred = credential.Credential(secret_id, secret_key)
        # 实例化一个http选项，可选的，没有特殊需求可以跳过
        http_profile = HttpProfile()
        http_profile.endpoint = "tts.tencentcloudapi.com"
        # 实例化一个client选项，可选的，没有特殊需求可以跳过
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        # 实例化要请求产品的client对象,clientProfile是可选的
        self.tencent_tts_client=tts_client.TtsClient(cred, region, client_profile)
        
        super().__init__(config)
    
    # 创建一个语音合成任务，腾讯云长文本
    def create_tts_task(self, text, VoiceType=501003, EnableSubtitle=False):
        
        # 实例化一个请求对象,每个接口都会对应一个request对象
        req = models.CreateTtsTaskRequest()
        params = {
            "Text": text,
            "VoiceType": int(VoiceType),
            "EnableSubtitle": EnableSubtitle
        }
        req.from_json_string(json.dumps(params))
        
        # 返回的resp是一个CreateTtsTaskResponse的实例，与请求对象对应
        resp = self.tencent_tts_client.CreateTtsTask(req)
        # 输出json格式的字符串回包
        return resp
    
    # 获取一个语音合成任务的状态
    def get_tts_task_status(self, TaskId):
        
        # 实例化一个请求对象,每个接口都会对应一个request对象
        req = models.DescribeTtsTaskStatusRequest()
        params = {
            "TaskId": TaskId
        }
        req.from_json_string(json.dumps(params))

        # 返回的resp是一个DescribeTtsTaskStatusResponse的实例，与请求对象对应
        resp = self.tencent_tts_client.DescribeTtsTaskStatus(req)
        # 输出json格式的字符串回包
        return resp
    
    # 下载合成任务生成的音频文件
    def download_audio(self, url, save_path):
        try:
            # 发送HTTP GET请求
            response = requests.get(url, stream=True)
            response.raise_for_status()  # 检查请求是否成功

            # 将文件内容写入本地
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            print(f"文件已下载到: {save_path}")
        except requests.exceptions.RequestException as e:
            print(f"下载失败: {e}")
    
    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):
        # print(f"{text}")
        # print(f"{output_file}")
        tts_task = self.create_tts_task(text, VoiceType=self.config.voice_name)
        print(f"- response: {tts_task}")
        task_id = tts_task.Data.TaskId
        
        while True:
            task_status = self.get_tts_task_status(task_id)
            task_status_str = task_status.Data.StatusStr
            print(f"- tasks status: {task_status_str}")
            if task_status_str == 'success':
                tts_download_url = task_status.Data.ResultUrl
                print(f"- download: {tts_download_url}")
                break
            sleep(5)
        
        self.download_audio(task_status.Data.ResultUrl, output_file)
        
        set_audio_tags(output_file, audio_tags)
    
    def get_output_file_extension(self):
        if self.config.output_format.endswith("mp3"):
            return "mp3"
        else:
            # Only mp3 supported 
            raise NotImplementedError(
                f"Unknown file extension for output format: {self.config.output_format}. Only mp3 supported in tencentcloud. See https://cloud.tencent.com/document/product/1073/57373."
            )
    def get_break_string(self):
        return " @BRK#"
    
    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price
    
    def validate_config(self):
        pass   