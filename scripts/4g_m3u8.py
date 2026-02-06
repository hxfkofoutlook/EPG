import cloudscraper
import base64
import uuid
import datetime
import hashlib
import time
import json
import sys
import re
import warnings
import os
from urllib.parse import urljoin, urlparse, parse_qs, quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import requests
import logging

# 關閉所有警告和日志
warnings.filterwarnings("ignore")

# 配置日志
logging.basicConfig(level=logging.ERROR)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True

# 默認配置
DEFAULT_USER_AGENT = "%E5%9B%9B%E5%AD%A3%E7%B7%9A%E4%B8%8A/4 CFNetwork/3826.500.131 Darwin/24.5.0"
DEFAULT_TIMEOUT = 30  # 增加超時時間
CHANNEL_DELAY = 1  # 增加頻道之間的延遲時間（秒）
MAX_RETRIES = 2  # 增加最大重試次數

# 默認賬號（可被環境變量覆蓋）
DEFAULT_USER = os.environ.get('GTV_USER', '')
DEFAULT_PASS = os.environ.get('GTV_PASS', '')

# 代理設置（從環境變量讀取）
HTTP_PROXY = os.environ.get('http_proxy', '') or os.environ.get('HTTP_PROXY', '')
HTTPS_PROXY = os.environ.get('https_proxy', '') or os.environ.get('HTTPS_PROXY', '')

# 內存緩存
cache_play_urls = {}
CACHE_EXPIRATION_TIME = 86400  # 24小時有效期

# 額外添加的博斯頻道列表
EXTRA_CHANNELS = [
    {
        "fs4GTV_ID": "4gtv-live404",
        "fnID": 265,
        "fsNAME": "博斯運動一台",
        "fsTYPE_NAME": "運動健康生活",
        "fsLOGO_MOBILE": "https://cdn.jsdelivr.net/gh/wanglindl/TVlogo@main/img/sportcast1.png"
    },
    {
        "fs4GTV_ID": "4gtv-live405",
        "fnID": 264,
        "fsNAME": "博斯高球台",
        "fsTYPE_NAME": "運動健康生活",
        "fsLOGO_MOBILE": "https://cdn.jsdelivr.net/gh/wanglindl/TVlogo@main/img/sportcast3.png"
    },
    {
        "fs4GTV_ID": "4gtv-live406",
        "fnID": 267,
        "fsNAME": "博斯網球台",
        "fsTYPE_NAME": "運動健康生活",
        "fsLOGO_MOBILE": "https://cdn.jsdelivr.net/gh/wanglindl/TVlogo@main/img/sportcast5.png"
    },
    {
        "fs4GTV_ID": "4gtv-live407",
        "fnID": 266,
        "fsNAME": "博斯無限台",
        "fsTYPE_NAME": "運動健康生活",
        "fsLOGO_MOBILE": "https://cdn.jsdelivr.net/gh/wanglindl/TVlogo@main/img/sportcast7.png"
    }
]


def is_github_actions():
    """檢查是否在 GitHub Actions 環境中運行"""
    return os.environ.get('GITHUB_ACTIONS') == 'true'


def get_proxies():
    """從環境變量獲取代理設置"""
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY

    if proxies:
        if is_github_actions():
            print(f"🔌 GitHub Actions 環境中使用代理: {proxies}")
        else:
            print(f"🔌 使用代理: {proxies}")
    else:
        if is_github_actions():
            print("🔌 GitHub Actions 環境中未設置代理，使用直接連接")
        else:
            print("🔌 未設置代理，使用直接連接")

    return proxies if proxies else None


def test_proxy_connection(scraper, timeout=10):
    """測試代理連接是否正常"""
    try:
        test_url = "https://httpbin.org/ip"
        response = scraper.get(test_url, timeout=timeout)
        if response.status_code == 200:
            print("✅ 代理連接測試成功")
            return True
        else:
            print(f"⚠️ 代理連接測試失敗，狀態碼: {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ 代理連接測試失敗: {e}")
        return False


def create_scraper_with_proxy(ua):
    """創建帶有代理設置的 scraper"""
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": ua})

    # 設置代理
    proxies = get_proxies()
    if proxies:
        try:
            scraper.proxies.update(proxies)

            # 在非 GitHub Actions 環境中測試代理連接
            if not is_github_actions():
                if not test_proxy_connection(scraper):
                    print("⚠️ 代理連接測試失敗，將使用直接連接")
                    scraper.proxies.clear()
        except Exception as e:
            print(f"⚠️ 代理設置失敗: {e}，將使用直接連接")
            scraper.proxies.clear()

    return scraper


def generate_uuid(user):
    """根據賬號和當前日期生成唯一 UUID，確保不同用戶每天 UUID 不同"""
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    name = f"{user}-{today}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name)).upper()


def generate_4gtv_auth():
    head_key = "PyPJU25iI2IQCMWq7kblwh9sGCypqsxMp4sKjJo95SK43h08ff+j1nbWliTySSB+N67BnXrYv9DfwK+ue5wWkg=="
    KEY = b"ilyB29ZdruuQjC45JhBBR7o2Z8WJ26Vg"
    IV = b"JUMxvVMmszqUTeKn"
    decoded = base64.b64decode(head_key)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    decrypted = cipher.decrypt(decoded)
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len].decode('utf-8')
    today = datetime.datetime.utcnow().strftime('%Y%m%d')
    sha512 = hashlib.sha512((today + decrypted).encode()).digest()
    return base64.b64encode(sha512).decode()


def sign_in_4gtv(user, password, fsenc_key, auth_val, ua, timeout):
    url = "https://api2.4gtv.tv/AppAccount/SignIn"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "fsenc_key": fsenc_key,
        "fsdevice": "iOS",
        "fsversion": "3.2.8",
        "4gtv_auth": auth_val,
        "User-Agent": ua
    }
    payload = {"fsUSER": user, "fsPASSWORD": password, "fsENC_KEY": fsenc_key}
    scraper = create_scraper_with_proxy(ua)

    resp = scraper.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("Data") if data.get("Success") else None


def get_all_channels(ua, timeout):
    """獲取所有頻道集合的頻道，並去除重覆頻道"""
    channel_sets = [1, 4]  # 已知的頻道集合ID
    all_channels = []
    seen_channel_ids = set()  # 用於跟蹤已看到的頻道ID

    for set_id in channel_sets:
        print(f"📡 正在獲取頻道集合 {set_id}...")
        url = f'https://api2.4gtv.tv/Channel/GetChannelBySetId/{set_id}/pc/L/V'
        headers = {"accept": "*/*", "origin": "https://www.4gtv.tv", "referer": "https://www.4gtv.tv/", "User-AAgent": ua}
        scraper = create_scraper_with_proxy(ua)

        try:
            resp = scraper.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("Success"):
                channels = data.get("Data", [])
                for channel in channels:
                    channel_id = channel.get("fs4GTV_ID", "")
                    # 檢查是否已經處理過這個頻道
                    if channel_id not in seen_channel_ids:
                        seen_channel_ids.add(channel_id)
                        all_channels.append(channel)
                        print(f"   ✅ 添加頻道: {channel.get('fsNAME', '未知')}")
                    else:
                        print(f"   ⏭️  跳過重覆頻道: {channel.get('fsNAME', '未知')}")
        except Exception as e:
            print(f"   ❌ 獲取頻道集合 {set_id} 失敗: {e}")
            continue

    return all_channels


def get_4gtv_channel_url_with_retry(channel_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout, max_retries=MAX_RETRIES):
    """帶重試機制的獲取頻道URL函數"""
    # 檢查緩存
    current_time = time.time()
    cache_key = f"{channel_id}_{fnCHANNEL_ID}"
    if cache_key in cache_play_urls:
        cache_time, url = cache_play_urls[cache_key]
        if current_time - cache_time < CACHE_EXPIRATION_TIME:
            return url

    for attempt in range(max_retries):
        try:
            headers = {
                "content-type": "application/json; charset=utf-8",
                "fsenc_key": fsenc_key,
                "accept": "*/*",
                "fsdevice": "iOS",
                "fsvalue": "",
                "fsversion": "3.2.8",
                "4gtv_auth": auth_val,
                "Referer": "https://www.4gtv.tv/",
                "User-Agent": ua
            }
            payload = {
                "fnCHANNEL_ID": fnCHANNEL_ID,
                "clsAPP_IDENTITY_VALIDATE_ARUS": {"fsVALUE": fsVALUE, "fsENC_KEY": fsenc_key},
                "fsASSET_ID": channel_id,
                "fsDEVICE_TYPE": "mobile"
            }
            scraper = create_scraper_with_proxy(ua)

            print(f"   📡 請求參數: channel_id={channel_id}, fnCHANNEL_ID={fnCHANNEL_ID}")
            
            resp = scraper.post('https://api2.4gtv.tv/App/GetChannelUrl2', headers=headers, json=payload, timeout=timeout)
            
            # 檢查響應狀態
            print(f"   📊 響應狀態碼: {resp.status_code}")
            
            resp.raise_for_status()
            data = resp.json()
            
            # 打印調試信息
            if not data.get('Success'):
                print(f"   ❌ API返回失敗: {data.get('Message', '未知錯誤')}")
                print(f"   🔍 響應數據: {json.dumps(data, ensure_ascii=False)[:200]}...")
                
                # 檢查是否是權限問題
                if data.get('Message') and ('授權' in data.get('Message') or 'auth' in data.get('Message', '').lower()):
                    print("   ⚠️  可能是權限問題，該頻道可能需要特殊訂閱")
            
            if data.get('Success') and 'flstURLs' in data.get('Data', {}):
                url = data['Data']['flstURLs'][1]
                print(f"   ✅ 獲取URL成功: {url[:80]}...")
                # 更新緩存
                cache_play_urls[cache_key] = (current_time, url)
                return url
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ 獲取頻道 {channel_id} 失敗，正在重試 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(3)  # 重試前等待3秒
            else:
                print(f"❌ 獲取頻道 {channel_id} 失敗，已達到最大重試次數: {e}")
                # 打印詳細的錯誤信息
                import traceback
                print(f"   🔍 詳細錯誤: {traceback.format_exc()[:300]}")
                return None
    return None


def get_highest_bitrate_url(master_url):
    """嘗試獲取更高質量的URL - 只對特定開頭的網址進行處理"""
    # 只對以 "https://4gtvfree-mozai.4gtv.tv" 開頭的網址進行處理
    if master_url and master_url.startswith("https://4gtvfree-mozai.4gtv.tv") and 'index.m3u8' in master_url:
        print(f"   📶 嘗試獲取高質量URL (1080p)...")
        return master_url.replace('index.m3u8', '1080.m3u8')

    # 對於其他網址，保持原樣
    print(f"   📶 使用原始URL")
    return master_url


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='█', print_end="\r"):
    """
    打印進度條
    @params:
        iteration   - 當前進度 (Int)
        total       - 總數 (Int)
        prefix      - 前綴字符串 (Str)
        suffix      - 後綴字符串 (Str)
        decimals    - 小數位數 (Int)
        length      - 進度條長度 (Int)
        fill        - 進度條填充字符 (Str)
        print_end   - 結束字符 (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=print_end)
    # 如果完成，打印新行
    if iteration == total:
        print()


def generate_m3u_playlist(user, password, ua, timeout, output_dir="playlist", delay=CHANNEL_DELAY):
    """生成M3U播放列表"""
    try:
        # 創建輸出目錄
        os.makedirs(output_dir, exist_ok=True)

        print("🔑 正在生成認證信息...")
        # 生成認證信息
        fsenc_key = generate_uuid(user)
        auth_val = generate_4gtv_auth()
        fsVALUE = sign_in_4gtv(user, password, fsenc_key, auth_val, ua, timeout)

        if not fsVALUE:
            print("❌ 登錄失敗")
            return False

        print("📡 正在獲取頻道列表...")
        # 獲取所有頻道
        channels = get_all_channels(ua, timeout)

        if not channels:
            print("❌ 無法獲取頻道列表")
            return False

        print(f"📺 共找到 {len(channels)} 個頻道")
        
        # 添加額外指定的博斯頻道到頻道列表
        print("📡 添加額外博斯運動頻道...")
        for extra_channel in EXTRA_CHANNELS:
            # 檢查是否已經存在相同的頻道
            existing = False
            for channel in channels:
                if channel.get("fs4GTV_ID") == extra_channel["fs4GTV_ID"]:
                    existing = True
                    break
            
            if not existing:
                channels.append(extra_channel)
                print(f"   ✅ 添加額外頻道: {extra_channel['fsNAME']}")
            else:
                print(f"   ⏭️  跳過已存在的額外頻道: {extra_channel['fsNAME']}")
        
        print(f"📺 添加額外頻道後，總共 {len(channels)} 個頻道")

        # 創建M3U文件
        m3u_content = "#EXTM3U\n"
        successful_channels = 0
        failed_channels = 0
        failed_list = []

        # 顯示進度條
        print("🚀 開始處理頻道:")
        total_channels = len(channels)

        for index, channel in enumerate(channels):
            channel_id = channel.get("fs4GTV_ID", "")
            channel_name = channel.get("fsNAME", "")
            channel_type = channel.get("fsTYPE_NAME", "其他")
            channel_logo = channel.get("fsLOGO_MOBILE", "")
            fnCHANNEL_ID = channel.get("fnID", "")

            # 處理頻道類型
            if channel_type:
                # 分割字符串並取第一部分
                channel_type = channel_type.split(',')[0]

            # 檢查是否為fast-live開頭，如果是則修改類型為FastTV飛速看
            if channel_id.startswith('fast-live'):
                channel_type = "FastTV飛速看"

            # 顯示當前處理的頻道信息
            print(f"\n[{index+1}/{total_channels}] 處理頻道: {channel_name}")
            print(f"   📺 頻道類型: {channel_type}")

            # 添加延遲
            time.sleep(delay)

            # 獲取頻道URL（帶重試機制）
            try:
                print(f"   🔗 獲取頻道URL...")
                stream_url = get_4gtv_channel_url_with_retry(channel_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout)
                
                if not stream_url:
                    # 如果是博斯頻道，嘗試使用備用方法
                    if channel_id in ["4gtv-live404", "4gtv-live405", "4gtv-live406", "4gtv-live407"]:
                        print(f"   ⚠️  博斯頻道 {channel_name} 無法獲取URL，嘗試使用備用方案...")
                        # 這里可以添加備用URL，如果有的話
                        # 例如：stream_url = f"https://example.com/backup/{channel_id}.m3u8"
                        print(f"   ℹ️  目前沒有備用URL，需要手動添加")
                    
                    print(f"   ❌ 無法獲取頻道 {channel_name} 的URL")
                    failed_channels += 1
                    failed_list.append((channel_name, "無法獲取URL"))
                    continue

                # 嘗試獲取更高質量的URL（僅對特定域名）
                highest_url = get_highest_bitrate_url(stream_url)

                # 添加到M3U內容
                m3u_content += f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}" tvg-logo="{channel_logo}" group-title="{channel_type}",{channel_name}\n'
                m3u_content += f"{highest_url}\n"

                print(f"   ✅ 已添加頻道: {channel_name}")
                successful_channels += 1

            except Exception as e:
                print(f"   ❌ 處理頻道 {channel_name} 時出錯: {e}")
                failed_channels += 1
                failed_list.append((channel_name, str(e)))
                continue

            # 更新進度條
            print_progress_bar(index + 1, total_channels, prefix='進度:', suffix=f'完成 {index+1}/{total_channels}')

        # 寫入文件
        output_path = os.path.join(output_dir, "4gtv.m3u")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(m3u_content)

        print(f"\n🎉 播放列表生成完成: {output_path}")
        print(f"✅ 成功處理: {successful_channels} 個頻道")
        print(f"❌ 失敗處理: {failed_channels} 個頻道")

        if failed_list:
            print("\n📋 失敗頻道清單:")
            for channel_name, error in failed_list:
                print(f"   - {channel_name}: {error}")
                
            # 如果有失敗的博斯頻道，顯示額外信息
            bos_channels = [ch for ch in failed_list if "博斯" in ch[0]]
            if bos_channels:
                print(f"\n⚠️  博斯頻道獲取失敗可能原因:")
                print(f"   1. 需要特殊訂閱或套餐")
                print(f"   2. 頻道ID可能已更改")
                print(f"   3. 地區限制或IP限制")
                print(f"   4. 您可以嘗試手動登錄4gtv網站查看這些頻道是否可用")

        return True

    except Exception as e:
        print(f"❌ 生成播放列表時出錯: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函數，提供命令行界面"""
    import argparse

    parser = argparse.ArgumentParser(description='4GTV 流媒體獲取工具')
    parser.add_argument('--generate-playlist', action='store_true', help='生成M3U播放列表')
    parser.add_argument('--user', type=str, default=DEFAULT_USER, help='用戶名')
    parser.add_argument('--password', type=str, default=DEFAULT_PASS, help='密碼')
    parser.add_argument('--ua', type=str, default=DEFAULT_USER_AGENT, help='用戶代理')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='超時時間(秒)')
    parser.add_argument('--output-dir', type=str, default="playlist", help='輸出目錄')
    parser.add_argument('--delay', type=float, default=CHANNEL_DELAY, help='頻道之間的延遲時間(秒)')
    parser.add_argument('--retries', type=int, default=MAX_RETRIES, help='最大重試次數')
    parser.add_argument('--verbose', action='store_true', help='顯示詳細處理信息')
    parser.add_argument('--proxy', type=str, help='代理服務器（例如: http://username:password@proxy.com:port）')
    parser.add_argument('--no-proxy', action='store_true', help='強制不使用代理')

    args = parser.parse_args()

    # 設置代理（命令行參數優先於環境變量）
    global HTTP_PROXY, HTTPS_PROXY

    if args.no_proxy:
        HTTP_PROXY = ''
        HTTPS_PROXY = ''
        print("🔌 強制禁用代理")
    elif args.proxy:
        HTTP_PROXY = args.proxy
        HTTPS_PROXY = args.proxy
        print(f"🔌 使用命令行指定的代理: {args.proxy}")

    if args.generate_playlist:
        success = generate_m3u_playlist(
            args.user,
            args.password,
            args.ua,
            args.timeout,
            args.output_dir,
            args.delay
        )
        return 0 if success else 1
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
