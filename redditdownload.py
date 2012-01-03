"""Download images from a reddit.com subreddit."""

import re
import StringIO
from urllib2 import urlopen, HTTPError, URLError
from httplib import InvalidURL
from argparse import ArgumentParser
from os.path import exists as pathexists, join as pathjoin, basename as pathbasename
from os import mkdir
from reddit import getitems


class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""


def _extractImgurAlbumUrls(albumUrl):
    """
    Given an imgur album URL, attempt to extract the images within that
    album

    Returns:
        List of qualified imgur URLs
    """
    response = urlopen(albumUrl)
    info = response.info()

    # Rudimentary check to ensure the URL actually specifies an HTML file
    if 'content-type' in info and not info['content-type'].startswith('text/html'):
        return []

    filedata = response.read()

    m = re.compile(r'\"hash\":\"(.[^\"]*)\"')

    items = []

    fp = StringIO.StringIO(filedata)

    for line in fp.readlines():
        results = re.findall(m, line)
        if not results:
            continue

        items += results

    fp.close()

    urls = ['http://i.imgur.com/%s.jpg' % (hash) for hash in items]

    return urls


def _downloadFromUrl(url, destDir):
    """
    Attempt to download file specified by url to 'destDir'

    Returns:
        Filename (derived from url and appended to 'destDir')

    Raises:
        WrongFileTypeException

            when content-type is not in the supported types or cannot
            be derived from the URL

        FileExceptionsException

            If the filename (derived from the URL) already exists in
            the destination directory.
    """
    RESPONSE = urlopen(url)
    INFO = RESPONSE.info()

    # Work out file type either from the response or the url.
    if 'content-type' in INFO.keys():
        FILETYPE = INFO['content-type']
    elif url.endswith('.jpg') or url.endswith('.jpeg'):
        FILETYPE = 'image/jpeg'
    elif url.endswith('.png'):
        FILETYPE = 'image/png'
    else:
        FILETYPE = 'unknown'

    # Only try to download acceptable image types
    if not FILETYPE in ['image/jpeg', 'image/png']:
        raise WrongFileTypeException('WRONG FILE TYPE: %s has type: %s!' % (url, FILETYPE))

    FILENAME = pathjoin(ARGS.dir, pathbasename(url))

    # Don't download files multiple times!
    if pathexists(FILENAME):
        raise FileExistsException('URL [%s] already downloaded.' % (url))

    FILEDATA = RESPONSE.read()
    FILE = open(FILENAME, 'wb')
    FILE.write(FILEDATA)
    FILE.close()

    return FILENAME


def _processImgurUrl(url):
    """
    Given an imgur URL, determine if it's a direct link to an image or an
    album.  If the latter, attempt to determine all images within the album

    Returns:
        list of imgur URLs
    """
    if 'imgur.com/a/' in url:
        return _extractImgurAlbumUrls(url)

    # Change .png to .jpg for imgur urls.
    if url.endswith('.png'):
        url = url.replace('.png', '.jpg')
    # Add .jpg to imgur urls that are missing it.
    elif '.jpg' not in url:
        url = '%s.jpg' % url

    return [url]


def _extractUrls(url):
    urls = []

    if 'imgur.com' in ITEM['url']:
        urls = _processImgurUrl(ITEM['url'])
    else:
        urls = [ITEM['url']]

    return urls

if __name__ == "__main__":
    PARSER = ArgumentParser(description='Downloads files with specified extension from the specified subreddit.')
    PARSER.add_argument('reddit', metavar='<subreddit>', help='Subreddit name.')
    PARSER.add_argument('dir', metavar='<destdir>', help='Dir to put downloaded files in.')
    PARSER.add_argument('-last', metavar='l', default='', required=False, help='ID of the last downloaded file.')
    PARSER.add_argument('-score', metavar='s', default=0, type=int, required=False, help='Minimum score of images to download.')
    PARSER.add_argument('-num', metavar='n', default=0, type=int, required=False, help='Number of images to download.')
    PARSER.add_argument('-update', default=False, action='store_true', required=False, help='Run until you encounter a file already downloaded.')
    PARSER.add_argument('-sfw', default=False, action='store_true', required=False, help='Download safe for work images only.')
    PARSER.add_argument('-nsfw', default=False, action='store_true', required=False, help='Download NSFW images only.')
    PARSER.add_argument('-regex', default=None, action='store', required=False, help='Use Python regex to filter based on title.')
    PARSER.add_argument('-verbose', default=False, action='store_true', required=False, help='Enable verbose output.')
    ARGS = PARSER.parse_args()

    print 'Downloading images from "%s" subreddit' % (ARGS.reddit)

    nTotal = nDownloaded = nErrors = nSkipped = nFailed = 0
    FINISHED = False

    # Create the specified directory if it doesn't already exist.
    if not pathexists(ARGS.dir):
        mkdir(ARGS.dir)

    # If a regex has been specified, compile the rule (once)
    reRule = None
    if ARGS.regex:
        reRule = re.compile(ARGS.regex)

    LAST = ARGS.last

    while not FINISHED:
        ITEMS = getitems(ARGS.reddit, LAST)
        if not ITEMS:
            # No more items to process
            break

        for ITEM in ITEMS:
            nTotal += 1

            if ITEM['score'] < ARGS.score:
                if ARGS.verbose:
                    print '    SCORE: %s has score of %s which is lower than required score of %s.' % (ITEM['id'], ITEM['score'], ARGS.score)

                nSkipped += 1
                continue
            elif ARGS.sfw and ITEM['over_18']:
                if ARGS.verbose:
                    print '    NSFW: %s is marked as NSFW.' % (ITEM['id'])

                nSkipped += 1
                continue
            elif ARGS.nsfw and not ITEM['over_18']:
                if ARGS.verbose:
                    print '    Not NSFW, skipping %s' % (ITEM['id'])

                nSkipped += 1
                continue
            elif ARGS.regex and not re.match(reRule, ITEM['title']):
                if ARGS.verbose:
                    print '    Regex match failed'

                nSkipped += 1
                continue

            for url in _extractUrls(ITEM['url']):
                try:
                    FILENAME = _downloadFromUrl(url, ARGS.dir)

                    # Image downloaded successfully!
                    print '    Downloaded URL [%s].' % (url)
                    nDownloaded += 1

                    if ARGS.num > 0 and nDownloaded >= ARGS.num:
                        FINISHED = True
                        break
                except WrongFileTypeException as ERROR:
                    print '    %s' % (ERROR)
                    nSkipped += 1
                except FileExistsException as ERROR:
                    print '    %s' % (ERROR)
                    nErrors += 1
                    if ARGS.update:
                        print '    Update complete, exiting.'
                        FINISHED = True
                        break
                except HTTPError as ERROR:
                    print '    HTTP ERROR: Code %s for %s.' % (ERROR.code, url)
                    nFailed += 1
                except URLError as ERROR:
                    print '    URL ERROR: %s!' % (url)
                    nFailed += 1
                except InvalidURL as ERROR:
                    print '    Invalid URL: %s!' % (url)
                    nFailed += 1

            if FINISHED:
                break

        LAST = ITEM['id']

    print 'Downloaded %d files (Processed %d, Skipped %d, Exists %d)' % (nDownloaded, nTotal, nSkipped, nErrors)
