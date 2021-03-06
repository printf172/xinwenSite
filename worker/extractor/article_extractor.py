# -*- coding: utf-8 -*-
import json
import os
import sys
import traceback

from flask import jsonify
from lxml import etree

import re
import worker.utils.tools as tools
from worker.extractor.config import *
from ulogger import setLogger

log_path = str(os.path.dirname(os.path.abspath(__file__)))
logger=setLogger(log_path,"ArticleExtractor")

class ArticleExtractor():
    def __init__(self, url, html = None, language='zh'):
        self._html = html
        self._url = url

        self._content_start_pos = ''
        self._content_end_pos = ''
        self._content_center_pos = ''
        self._paragraphs = ''

        if not html:
            self._html = tools.get_html(url)

        self._text = self.__del_html_tag(self._html, save_useful_tag = True)

    def __replace_str(self, source_str, regex, replace_str = ''):
        '''
        @summary: 替换字符串
        ---------
        @param source_str: 原字符串
        @param regex: 正则
        @param replace_str: 用什么来替换 默认为''
        ---------
        @result: 返回替换后的字符串
        '''
        str_info = re.compile(regex)
        return str_info.sub(replace_str, source_str)

    def __del_html_tag(self, html, save_useful_tag = False):
        '''
        @summary:
        ---------
        @param html:
        @param save_useful_tag:保留有用的标签，如img和p标签
        ---------
        @result:
        '''
        html = self.__replace_str(html, '(?i)<script(.|\n)*?</script>') #(?i)忽略大小写
        html = self.__replace_str(html, '(?i)<style(.|\n)*?</style>')
        html = self.__replace_str(html, '<!--(.|\n)*?-->')
        html = self.__replace_str(html, '(?!&[a-z]+=)&[a-z]+;?', ' ') # 干掉&nbsp等无用的字符 但&xxx= 这种表示参数的除外

        if save_useful_tag:
            html = self.__replace_str(html, r'(?!{useful_tag})<(.|\n)+?>'.format(useful_tag = '|'.join(USEFUL_TAG)))
        else:
            html = self.__replace_str(html, '<(.|\n)*?>')

        html = self.__replace_str(html, '[\f\r\t\v]') # 将空格和换行符外的其他空白符去掉
        html = html.strip()
        return html

    def __del_unnecessary_character(self, content):
        '''
        @summary: 去掉多余的换行和空格
        ---------
        @param content:
        ---------
        @result:
        '''
        content = content.strip()
        content = content[content.find('>') + 1 : ] if content.startswith('</') else content # 去掉开头的结束符
        content = self.__replace_str(content, ' {2,}', '') # 去掉超过一个的空格
        return self.__replace_str(content, '(?! )\s+', '\n') # 非空格的空白符转换为回车

    def get_title(self, special_title_regex, special_title_xpath):
        title = ''

        title = self.extract_special_content(special_title_regex, special_title_xpath, sign='title')
        if not title:
            regexs = ['(?i)<title.*?>(.*?)</title>','<h1.*?>(.*?)</h1>','<h2.*?>(.*?)</h2>,<h3.*?>(.*?)</h3>','<h4.*?>(.*?)</h4>']
            title = tools.get_info(self._html, regexs, fetch_one = True)
            if title:
                title = title[:title.find('_')] if '_' in title else title
                title = title[:title.find('-')] if '-' in title else title
                title = title[:title.find('|')] if '|' in title else title
        title = tools.del_html_tag(title)
        return title

    def get_content(self,special_content_xpath):
        '''
        @summary:
        基于文本密度查找正文
            1、将html去标签，将空格和换行符外的其他空白符去掉
            2、统计连续n段文字的长度，此处用于形容一定区域的文本密度
            3、将文本最密集处当成正文的开始和结束位置
            4、在正文开始处向上查找、找到文本密度小于等于正文文本密度阈值值，算为正文起始位置。该算法文本密度阈值值为文本密度值的最小值
            5、在正文开始处向下查找、找到文本密度小于等于正文文本密度阈值值，算为正文结束位置。该算法文本密度阈值值为文本密度值的最小值

        去除首页等干扰项：
            1、正文一般都包含p标签。此处统计p标签内的文字数占总正文文字数的比例。超过一定阈值，则算为正文
        待解决：
            翻页 如：http://mini.eastday.com/a/171205202028050-3.html
        ---------
        ---------
        @result:
        '''
        content = ''
        html = etree.HTML(self._html)
        # 处理特殊的网站不规则的内容-xpath
        if special_content_xpath:
            content = html.xpath(special_content_xpath)
            if content:
                content = content[0]
                try:
                    content = etree.tostring(content, encoding="utf-8").decode("utf-8")
                    content = self.__del_html_tag(content, True)
                    content = self.__del_unnecessary_character(content)
                except:
                    return content
                return content
        # 没有匹配到，根据配置文件的规则匹配
        for xpath in SPECIAL_CONTENT_XPATH:
            content = html.xpath(xpath)
            if content:
                content = content[0]
                try:
                    content = etree.tostring(content, encoding="utf-8").decode("utf-8")
                    content = self.__del_html_tag(content, True)
                    content = self.__del_unnecessary_character(content)
                    return content
                except:
                    return content             


        paragraphs = self._text.split('\n')
        # for i, paragraph in enumerate(paragraphs):
        #     print(i, paragraph)

        # 统计连续n段的文本密度
        paragraph_lengths = [len(self.__del_html_tag(paragraph)) for paragraph in paragraphs]
        # paragraph_lengths = [len(paragraph.strip()) for paragraph in paragraphs]
        paragraph_block_lengths = [sum(paragraph_lengths[i : i + MAX_PARAGRAPH_DISTANCE]) for i in range(len(paragraph_lengths))]  # 连续n段段落长度的总和（段落块），如段落长度为[0,1,2,3,4] 则连续三段段落长度为[3,6,9,3,4]

        self._content_center_pos = content_start_pos = content_end_pos = paragraph_block_lengths.index(max(paragraph_block_lengths)) #文章的开始和结束位置默认在段落块文字最密集处
        min_paragraph_block_length = MIN_PARAGRAPH_LENGHT * MAX_PARAGRAPH_DISTANCE
        # 段落块长度大于最小段落块长度且数组没有越界，则看成在正文内。开始下标继续向上查找
        while content_start_pos > 0 and paragraph_block_lengths[content_start_pos] > min_paragraph_block_length:
            content_start_pos -= 1

        # 段落块长度大于最小段落块长度且数组没有越界，则看成在正文内。结束下标继续向下查找
        while content_end_pos < len(paragraph_block_lengths) and paragraph_block_lengths[content_end_pos] > min_paragraph_block_length:
            content_end_pos += 1

        # 处理多余的换行和空白符
        content = paragraphs[content_start_pos : content_end_pos]
        content = '\n'.join(content)
        content = self.__del_unnecessary_character(content)
        if content:
            return content
        return ''

        # 此处统计p标签内的文字数占总正文文字数的比例。超过一定阈值，则算为正文
        # paragraphs_text_len = len(self.__del_html_tag(''.join(tools.get_info(content, '<p.*?>(.*?)</p>'))))
        # content_text_len = len(self.__del_html_tag(content))
        # if content_text_len and content_text_len > MIN_COUNTENT_WORDS and ((paragraphs_text_len / content_text_len) > MIN_PARAGRAPH_AND_CONTENT_PROPORTION):
        #     self._content_start_pos = content_start_pos
        #     self._content_end_pos = content_end_pos
        #     self._paragraphs = paragraphs
        #     # print(content_start_pos, content_end_pos, self._content_center_pos)
        #     return content
        # else:
        #     paragraphs_text_len = len(self.__del_html_tag(''.join(tools.get_info(content, '<span.*?>(.*?)</span>'))))
        #     content_text_len = len(self.__del_html_tag(content))
        #     if content_text_len and content_text_len > MIN_COUNTENT_WORDS and ((paragraphs_text_len / content_text_len) > MIN_PARAGRAPH_AND_CONTENT_PROPORTION):
        #         self._content_start_pos = content_start_pos
        #         self._content_end_pos = content_end_pos
        #         self._paragraphs = paragraphs
        #         # print(content_start_pos, content_end_pos, self._content_center_pos)
        #         return content
        # return ''

    def get_author(self, special_author_xpath, special_author_regex):

        author = self.extract_special_content(special_author_regex, special_author_xpath, sign='author')
        if author:
            return tools.del_html_tag(author)

        # 不去掉标签匹配
        author = tools.get_info(self._text, AUTHOR_REGEXS_TEXT, fetch_one = True)

        if not author: # 没有匹配到，去掉标签后进一步匹配，有的作者和名字中间有标签
            author = tools.get_info(self.__replace_str(self._text, '<(.|\n)*?>', ' '), AUTHOR_REGEXS_TEXT, fetch_one = True)

        if not author: # 仍没匹配到，则在html的author中匹配
            author = tools.get_info(self._html, AUTHOR_REGEX_TAG, fetch_one = True)

        return author

    def get_release_time_old(self):

        if self._content_start_pos and self._content_end_pos:
            content = self.__replace_str('\n'.join(self._paragraphs[self._content_start_pos  - RELEASE_TIME_OFFSET: self._content_end_pos + RELEASE_TIME_OFFSET]), '<(.|\n)*?>', '<>')
        else:
            content = self.__replace_str(self._text, '<(.|\n)*?>', '<>')

        release_time = tools.get_info(content, DAY_TIME_REGEXS, fetch_one = True)
        if not release_time:
            release_time = tools.get_info(self.__replace_str(self._text, '<(.|\n)*?>', '<>'), DAY_TIME_REGEXS, fetch_one = True)

        release_time = tools.format_date(release_time)

        return release_time

    def get_release_time_all(self):
        release_time = tools.get_info(self._html, DAY_TIME_REGEXS, fetch_one = True)
        release_time = tools.format_date(release_time)
        return release_time

    def extract_special_content(self, special_content_regex, special_content_xpath, sign):
        # 处理特殊的网站不规则的内容-regex
        if special_content_regex:
            content = tools.get_info(self._html, special_content_regex, fetch_one = True)
            if content:
                return content
            return ''
        # 处理特殊的网站不规则的内容-xpath
        if special_content_xpath:
            html = etree.HTML(self._html)
            content = html.xpath(special_content_xpath)
            if content:
                if type(content)==list:
                    content = content[0]
                return content
            return ''
        #没有匹配到，则按配置文件的规则进行匹配
        if sign == 'title':
            regex_expression = SPECIAL_TITLE_REGEX
            xpath_expression = SPECIAL_TITLE_XPATH
        elif sign == 'author':
            regex_expression = []
            xpath_expression = SPECIAL_AUTHOR_XPATH
        elif sign == 'time':
            regex_expression = SPECIAL_TIME__REGEX
            xpath_expression = SPECIAL_TIME_XPATH
        for xpath in xpath_expression:
            html = etree.HTML(self._html)
            content = html.xpath(xpath)
            if content:
                if type(content)==list:
                    content = content[0]
                return content
        content = tools.get_info(self._html, regex_expression, fetch_one = True)
        if content:
            return content
        return ''

    def get_release_time(self, special_time_regex, special_time_xpath):

        release_time = self.extract_special_content(special_time_regex, special_time_xpath, sign='time')
        if release_time:
            return tools.format_date(release_time)

        def get_release_time_in_paragraph(paragraph_pos):
            if self._paragraphs:
                while paragraph_pos >= 0:
                    content = self.__replace_str(self._paragraphs[paragraph_pos], '<(.|\n)*?>', '<>')
                    release_time = tools.get_info(content, DAY_TIME_REGEXS, fetch_one = True)
                    if release_time:
                        return tools.format_date(release_time)
                    paragraph_pos -= 1

            return None

        release_time = get_release_time_in_paragraph(self._content_start_pos)
        if not release_time:
            release_time = get_release_time_in_paragraph(self._content_center_pos)

        return release_time

    def get_html(url, special_title_regex, special_title_xpath, special_content_xpath, special_time_regex, special_time_xpath, special_author_xpath, special_author_regex,cookies=None):
        try:
            html = tools.get_html(url,cookies)

            article_extractor = ArticleExtractor(url, html)
            content = article_extractor.get_content(special_content_xpath)
            title = article_extractor.get_title(special_title_regex, special_title_xpath)
            release_time = article_extractor.get_release_time(special_time_regex, special_time_xpath)
            if not release_time:
                release_time = article_extractor.get_release_time_old()
            if not release_time:
                release_time = article_extractor.get_release_time_all()

            author = article_extractor.get_author(special_author_xpath, special_author_regex)
            return jsonify({"title": title, "content": content, "release_time": release_time, "author": author})

        except Exception:
            return traceback.format_exc()


if __name__ == '__main__':
    urls = [
        'http://www.eq.gov.cn/zwgk_97654/xwzx/tpxw_97856/202104/t20210401_2866380.html'

    ]
    for url in urls:
        html = tools.get_html(url)

        article_extractor = ArticleExtractor(url, html)
        content = article_extractor.get_content()
        title = article_extractor.get_title()
        release_time = article_extractor.get_release_time()
        if not release_time:
            release_time = article_extractor.get_release_time_old()
        if not release_time:
            release_time = article_extractor.get_release_time_all()
        author = article_extractor.get_author()
        print('---------------------------')
        print(url)
        print('title : ', title)
        print('release_time: ', release_time)
        print('author: ', author)
        print('content : ', content)
        print('---------------------------')


