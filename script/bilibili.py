"""
==================================
Name:       Bilibili 爬虫脚本
Author:     ZSAIM
Created:    2020-03-05
Recently Update:      
Version:    0.1
License:    Apache-2.0
==================================
"""
from request import next_script, download, Optional, Option
from script import ScriptBaseClass, dbg
import ffmpeg
import json
import re

re_playinfo = re.compile(
    r'<script>'
    r'(?:[(?:\s/\*).*?(?:\*/)\s])*'
    r'window\.__playinfo__(?:[(?:\s/\*).*?(?:\*/)\s])*=(?:[(?:\s/\*).*?(?:\*/)\s])*'
    r'(.*?)'
    r'</script>')
re_initial_state = re.compile(
    r'<script>'
    r'(?:[(?:\s/\*).*?(?:\*/)\s])*'
    r'window\.__INITIAL_STATE__(?:[(?:\s/\*).*?(?:\*/)\s])*=(?:[(?:\s/\*).*?(?:\*/)\s])*'
    r'(.*?)'
    r'(?:[(?:\s/\*).*?(?:\*/)\s])*;.*?'
    r'</script>')

dash_params = {
    'avid': None,
    'cid': None,
    'qn': None,   # quality
    'type': '',
    'otype': 'json',
    'fnver': '0',
    'fnval': '16',
    'session': None
}

durl_params = {
    'avid': None,
    'cid': None,
    'qn': None,   # quality
    'type': '',
    'otype': 'json',
    'fnver': '0',
    'fnval': '0',
    'session': None

}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36',
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
}


class Bilibili(ScriptBaseClass):
    name = 'bilibili'
    version = 0.1
    author = 'ZSAIM'
    created_date = '2020/03/05'

    supported_domains = ['www.bilibili.com']
    quality_ranking = [116, 80, 74, 64, 32, 16]

    def _init(self):
        self.html_res = None
        self.html_parse = None

    def fast_get(self):
        """ 快速粗略获取必要的数据。
        至少上传数据:
            title:  处理的标题
        """
        html_res = self.request_get(self.url, headers=dict(headers))
        # 汇报处理情况。
        if html_res.status_code != 200:
            dbg.error('%s %s: %s' % (html_res.status_code, html_res.reason, html_res.url))
        else:
            dbg.success('%s %s: %s' % (html_res.status_code, html_res.reason, html_res.url))

        # 上传标题
        html_parse = bs4.BeautifulSoup(html_res.text, features='html.parser')
        dbg.upload(title=html_parse.find('h1').text)

    def run(self):
        html_res = self.request_get(self.url, headers=dict(headers))
        # 汇报处理情况。
        if html_res.status_code != 200:
            dbg.error('%s %s: %s' % (html_res.status_code, html_res.reason, html_res.url))
        else:
            dbg.success('%s %s: %s' % (html_res.status_code, html_res.reason, html_res.url))

        # 上传标题
        html_parse = bs4.BeautifulSoup(html_res.text, features='html.parser')
        dbg.upload(title=html_parse.find('h1').text)

        playinfo = self.parse_playinfo(html_res) or {}
        initial_state = self.parse_initial_state(html_res) or {}

        #
        if not initial_state:
            raise ValueError('initial_state参数无法正确解析。')
        if initial_state.get('videoData'):
            aid = initial_state['videoData']['aid']
            cid = initial_state['videoData']['cid']
        elif initial_state.get('epInfo'):
            aid = initial_state['epInfo']['aid']
            cid = initial_state['epInfo']['cid']
        else:
            raise ValueError('参数aid, cid未找到。')

        # 是否分页
        videos_p = initial_state['videoData']['videos']
        if videos_p > 1:
            # 获取分p列表
            pagelist_res = self.api_pagelist(aid)
            page_cids = [d['cid'] for d in pagelist_res['data']]
        else:
            page_cids = [cid]

        request_params = {
            'avid': aid,
            'cid': cid,
            'qn': self.quality,
            'session': playinfo.get('session', '')
        }

        results = []
        for cid in page_cids:
            request_params['cid'] = cid
            # api: playurl
            result = self.api_playurl(request_params)
            results.append(Optional(result))

        results.append(
            next_script('https://www.bilibili.com/video/BV15Z4y1x7uk', rule=1, quality=self.quality)
        )

        dbg.upload(items=results)

    def api_playurl(self, request_params):
        """ api: https://api.bilibili.com/x/player/playurl?
        这一接口获得的视频资源属于
        """
        optional_items = []
        request_header = dict(headers)
        request_header['Referer'] = self.url
        r = dict(dash_params)
        r.update(request_params)
        api_res = self.api_get('https://api.bilibili.com/x/player/playurl?', r)
        data = api_res['data']
        # dash
        dash = data.get('dash')

        if dash:
            # audio 选项
            audio = Optional([
                download(uri=audio['base_url'], headers=request_header)
                for audio in dash['audio']
            ])
            # v
            time_length = data['timelength'] / 1000
            for v in dash['video']:
                video_dl = download(uri=v['base_url'], headers=request_header)
                item_req = ffmpeg.concat_av([video_dl, audio])

                frame_rate = v['frame_rate'].split('/')
                frame_rate = int(frame_rate[0]) / int(frame_rate[1])
                size = None
                video_desc = {
                    'length': time_length,
                    'size': size,
                    'quality': v['id'],
                    'width': v['width'],
                    'height': v['height'],
                    'frame_rate': frame_rate,
                    'mime_type': v['mime_type'],
                }

                # 发送成功解析到视频的消息，并带上资源信息
                dbg.success('quality: %s\nresolution: %s x %s\nsize: %s\nurl: %s' % (
                    v['id'], v['width'], v['height'], size, v['base_url']
                ))
                optional_items.append(Option(item_req, descriptions=video_desc))
        # durl
        r = dict(durl_params)
        r.update(request_params)
        api_res = self.api_get('https://api.bilibili.com/x/player/playurl?', r)
        durl = api_res.get('data', {}).get('durl')
        if durl:
            for v in durl:
                video_dl = download(uri=v['url'], headers=request_header)
                item_req = video_dl
                # 不需要合并操作使用none 方法, 或着接提交下载请求
                dbg.success('quality: %s\nresolution: %s x %s\nsize: %s\nurl: %s' % (
                    request_params['qn'], 'unknown', 'unknown', v['size'], v['url']
                ))
                optional_items.append(Option(item_req, descriptions=v))

        return optional_items

    def playlist(self, aid):
        """ api: https://api.bilibili.com/x/player/pagelist?aid=%s&jsonp=jsonp
        分p列表
        """
        request_params = {
            'aid': aid,
            'jsonp': 'jsonp'
        }
        api_res = self.api_get('https://api.bilibili.com/x/player/pagelist?', request_params)
        return api_res

    def api_pagelist(self, aid):
        """ api: https://api.bilibili.com/x/player/pagelist?aid=%s&jsonp=jsonp
        分p列表
        """
        request_params = {
            'aid': aid,
            'jsonp': 'jsonp'
        }
        api_res = self.api_get('https://api.bilibili.com/x/player/pagelist?', request_params)
        if api_res['code'] != 0:
            raise ValueError('分p列表返回错误。message: %s' % api_res['message'])
        return api_res

    @staticmethod
    def parse_playinfo(html_res):
        # 解析 window.__playinfo__
        res_playinfo = re_playinfo.search(html_res.text)
        if res_playinfo is None:
            # dbg.error('')
            raise ValueError(res_playinfo)
        playinfo = json.loads(res_playinfo.group(1))
        return playinfo

    @staticmethod
    def parse_initial_state(html_res):
        # 解析 window.__INITIAL_STATE__
        res_initial_state = re_initial_state.search(html_res.text)
        if re_initial_state is None:
            # dbg.error('')
            raise ValueError(re_initial_state)
        initial_state = json.loads(res_initial_state.group(1))
        return initial_state


if __name__ == '__main__':
    # 重载基类
    from script.base import ScriptBaseClass
    import bs4

    # 继承基类
    # class Bilibili(Bilibili, ScriptBaseClass):
    #     pass

    bilibili = Bilibili.test('https://www.bilibili.com/video/av91721893', 100)
    print(bilibili)