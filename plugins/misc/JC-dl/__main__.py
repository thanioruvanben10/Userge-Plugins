import glob
from userge import userge, Message, pool, config
from userge.utils import time_formatter, humanbytes, get_custom_import_re
from .. import jcdl
from math import floor
import requests, json, subprocess
import os, sys
from time import time
import yt_dlp.utils

yt_dlp.utils.std_headers['User-Agent'] = 'JioOnDemand/1.5.2.1 (Linux;Android 4.4.2) Jio'

ytdl = get_custom_import_re(jcdl.YTDL_PYMOD)
LOGGER = userge.getLogger(__name__)

# define 
async def load_config():
    global ssotoken, uniqueID
    with open ("/app/userge/plugins/misc/jcdl/creds.txt", "r") as f:
        try:
            Creds = json.load(f)
            ssotoken = Creds['ssotoken']
            uniqueID = Creds['uniqueID']
        except json.JSONDecodeError:
            ssotoken = ''
            uniqueID = ''    

Request_URL = "https://prod.media.jio.com/apis/common/v3/playbackrights/get/"
Meta_URL = "https://prod.media.jio.com/apis/common/v3/metamore/get/"
OTPSendURL = "https://prod.media.jio.com/apis/common/v3/login/sendotp"
OTPVerifyURL = "https://prod.media.jio.com/apis/common/v3/login/verifyotp"
    
async def load_creds(creds):
    try:
        ssotoken = creds['ssoToken']
        uniqueID = creds['uniqueId']
    except KeyError:
        print ("Wrong OTP, Try again!")
        sys.exit()
    Creds = {
        "ssotoken" : ssotoken,
        "uniqueID" : uniqueID
    }
    with open("/app/userge/plugins/misc/jcdl/creds.txt", "w") as f:
        f.write(json.dumps(Creds))

async def get_manifest(VideoID):
    headers = {
    'authority': 'prod.media.jio.com',
    'pragma': 'no-cache',
    'ssotoken': ssotoken,
    'bitrates': 'true',
    'os': 'Android',
    'user-agent': 'JioOnDemand/1.5.2.1 (Linux;Android 4.4.2) Jio',
    'content-type': 'application/json',
    'accept': 'application/json, text/plain, */*',
    }
    response = requests.post(url = Request_URL + VideoID , data = '{"uniqueId":"' + uniqueID + '"}' , headers = headers)
    return json.loads(response.text)

async def get_m3u8(manifest):
    print("QUALITY : ", qual)
    m3u8 = manifest['mpd'][qual]
    return m3u8

async def mod_m3u8(url):
    mod = url.replace("jiovod.cdn.jio.com", "jiobeats.cdn.jio.com")
    lst = mod.split("/")
    lst[-1] = "chunklist.m3u8"
    mod = "/".join(lst)
    return mod

async def get_metadata(VideoID):
    response = requests.get(url = Meta_URL + VideoID, headers = {'os': 'Android'})
    return json.loads(response.text)

@pool.run_in_thread
def get_streams(nonDRM_m3u8_url, prog, starttime):
    print ("Downloading A/V")
    _opts = {'allow_unplayable_formats' : True,
             'no_warnings' : True,
             'logger' : LOGGER,
             'external_downloader': 'aria2c'
             }
    x = ytdl.YoutubeDL(_opts)
    x.add_progress_hook(prog)
    dloader = x.download(nonDRM_m3u8_url)
    print ("\nSuccessfully downloaded the stream!")
    return dloader

def get_streams_(nonDRM_m3u8_url,prog,starttime):
    print ("Downloading A/V")
    dloader=os.system(f'yt-dlp {nonDRM_m3u8_url} --allow-unplayable-formats --downloader aria2c --user-agent "JioOnDemand/1.5.2.1 (Linux;Android 4.4.2) Jio" -q --no-warnings') # + -P TEMP:{cachePath} -P HOME:{outPath}
    print ("\nSuccessfully downloaded the stream!")
    return dloader.prog()

@userge.on_cmd("jclogin", about={
    'header': "Sent Mobile Number Of Jio along with Command",
    'usage': "{tr}jclogin [JioMobile Number]",
    'examples': "{tr}jclogin 9876543210"})
async def jclogin_(message: Message):
    """ JC login """
    global send, mobile_number
    mobile_number = message.input_str
    send = requests.post(url = OTPSendURL, headers = {
    'authority': 'prod.media.jio.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'origin': 'https://www.jiocinema.com',
    'referer': 'https://www.jiocinema.com/',
    },
     data = '{"number":"+91' + mobile_number +'"}'
    )
    if 'success' in str(send.content):
        await message.edit(f"`Otp Send Successfully ...`")
    else:
        await message.edit(f"`Otp Not Sent ...`")

@userge.on_cmd("jcotp", about={
    'header': "Sent OTP that You Received along with command",
    'usage': "{tr}jcotp [One Time Password]",
    'examples': "{tr}jcotp xxxxxx"})
async def jcotp_(message: Message):
    """ JC OTP Send """
    if 'success' in str(send.content):
        OTP = message.input_str
        verify = requests.post(url = OTPVerifyURL, headers = {
        'authority': 'prod.media.jio.com',
        'pragma': 'no-cache',
        'origin': 'https://www.jiocinema.com',
        'referer': 'https://www.jiocinema.com/',
        'deviceid': '1727391720'
        },
        data = '{"number":"+91' + mobile_number + '","otp":"' + OTP + '"}')
        creds = json.loads(verify.content)
        await load_creds(creds)
        if load_creds(creds):
            await message.edit(f"`Otp Saved Successfully ...`")
        else:
            await message.edit(f"`Otp Not Saved ...`")
    else:
        await message.edit("Wrong/Unregistered Mobile Number (ensure there's no +91 or 0 in the beginning)")

@userge.on_cmd("jcdl", about={
    'header': "Jio Cinema Downloader",
    'description': "Download Jio Cinema Non Drm Links",
    'usage': "{tr}jcdl [Jiocinema Link]",
    'examples': "{tr}jcdl https://www.jiocinema.com/movies/a-film-by-aravind?type=0&id=72ef4b40a31011e98c560fc46432af32"})
async def jio_dl(message: Message) -> None:
    """ JC Download """
    try:
        global VideoID, qual
        edited = False
        startTime = c_time = time()

        def __progress(data: dict):
            nonlocal edited, c_time
            diff = time() - c_time
            #print(data)
            if (
                data['status'] == "downloading"
                and (not edited or diff >= config.Dynamic.EDIT_SLEEP_TIMEOUT)
            ):
                c_time = time()
                edited = True
                eta = data.get('eta')
                speed = data.get('speed')
                if not (eta and speed):
                    return
                out = "**Speed** >> {}/s\n**ETA** >> {}\n".format(
                    humanbytes(speed), time_formatter(eta))
                out += f'**File Name** >> `{data["filename"]}`\n\n'
                current = data.get('downloaded_bytes')
                total = data.get('total_bytes_estimate')
                if current and total:
                    percentage = int(current) * 100 / int(total)
                    out += f"Progress : {int(percentage)}%\n"
                    out += "[{}{}]".format(
                        ''.join((config.FINISHED_PROGRESS_STR
                                 for _ in range(floor(percentage / 5)))),
                        ''.join((config.UNFINISHED_PROGRESS_STR
                                 for _ in range(20 - floor(percentage / 5)))))
                userge.loop.create_task(message.edit(out))

        if '-h' in message.flags:
            qual = 'high'
        elif '-m' in message.flags:
            qual = 'medium'
        elif '-l' in message.flags:
            qual = 'low'
        link = message.filtered_input_str
        if "id=" in link:
            VideoID = link.split("id=")[-1]
        else:
            VideoID = link.split("/")[-3]
        await message.edit(f"`Downloading: {link} ...`")
        await load_config()
        manifest = await get_manifest(VideoID)
        metadata = await get_metadata(VideoID)
        try:
            content_name = metadata['name']
        except KeyError:
            await message.edit(f"`Incorrect/Malformed VideoID`")
        fileName = f'{content_name}.{metadata["year"]}.mp4'
        m3u8_url = await get_m3u8(manifest)
        nonDRM_m3u8_url = await mod_m3u8(m3u8_url)
        dwnld = await get_streams(nonDRM_m3u8_url,__progress,startTime)
        await message.edit(str(dwnld))
        os.rename(f'/app/chunklist [chunklist].mp4', fileName)
        await message.edit(f"`Download Done Successfully...`")
    except Exception as e:
        return await message.err(str(e))
