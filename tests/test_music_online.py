import io
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

import mido
from music_online import catalog, download, score_id, SameSiteRedirect, fetch
from music_service import MusicService

ID = 'e8191e2a-5bc7-4c5f-b180-d5b3dddd646c'
CARD = f'''<form class="library-search"></form><article class="score-card">
<a class="score-title" href="/scores/{ID}?returnTo=x">测试 &amp; 曲谱</a>
<p class="score-subtitle">作曲<!-- --> <span>·</span> 手碟</p>
<a class="byline">作者</a><span class="format-chip">MIDI</span></article>
<a href="/library?q=test&amp;page=2">下一页</a>'''


class OnlineTests(unittest.TestCase):
    def test_catalog_parses_visible_fields_and_pagination(self):
        with patch('music_online.fetch', return_value=CARD.encode()) as request:
            result = catalog('测试', 1, threading.Event())
        self.assertTrue(result['has_next'])
        self.assertEqual(result['items'][0]['title'], '测试 & 曲谱')
        self.assertEqual(result['items'][0]['format'], 'MIDI')
        self.assertEqual(result['items'][0]['author'], '作者')
        self.assertIn('page=1', request.call_args.args[0])

    def test_unexpected_html_and_invalid_ids_are_rejected(self):
        with patch('music_online.fetch', return_value=b'<h1>Access denied</h1>'):
            with self.assertRaises(ValueError):
                catalog('', 1, threading.Event())
        for value in ('../../x', 'https://evil.test', None):
            with self.assertRaises(ValueError):
                score_id(value)

    def test_download_requires_valid_midi(self):
        detail = f'<h1>曲名</h1><a href="/api/scores/{ID}/file?download=1&amp;version=abc">下载</a>'.encode()
        with patch('music_online.fetch', side_effect=[detail, b'<html>error</html>']):
            with self.assertRaisesRegex(ValueError, 'MIDI'):
                download(ID, threading.Event())

    def test_redirect_cannot_leave_site(self):
        with self.assertRaises(ValueError):
            SameSiteRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test/file')

    def test_fetch_cancel_and_size_limit(self):
        for cancelled in (True, False):
            stop = threading.Event()
            if cancelled:
                stop.set()
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b'12345'
            with patch('music_online.build_opener') as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(ValueError):
                    fetch('/library', stop, limit=4)

    def test_download_job_imports_once_and_never_sends_keys(self):
        midi = mido.MidiFile()
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.Message('note_on', note=60, velocity=80, time=0))
        track.append(mido.Message('note_off', note=60, time=480))
        buffer = io.BytesIO()
        midi.save(file=buffer)
        with tempfile.TemporaryDirectory() as directory:
            factory = Mock(side_effect=AssertionError('No real input'))
            service = MusicService(directory, backend_factory=factory, monitor=False)
            try:
                with patch('music_online.download', return_value=(buffer.getvalue(), '在线测试', 'https://rocomusic.cn/file')):
                    for _ in range(2):
                        service.handle('online_download', {'id': ID})
                        service.job_thread.join(5)
                        self.assertEqual(service.job['state'], 'done', service.job)
                self.assertEqual(len(service.library.items), 1)
                self.assertEqual(service.library.items[0]['title'], '在线测试')
                factory.assert_not_called()
                self.assertFalse(service.player.running)
                service.job_stop.set()
            finally:
                service.shutdown()

    def test_search_is_cancellable_without_blocking_state_or_committing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MusicService(directory, backend_factory=Mock(), monitor=False)
            entered, release = threading.Event(), threading.Event()
            def slow_catalog(*args):
                entered.set()
                release.wait(3)
                return {'items': [], 'query': '', 'page': 1, 'has_next': False}
            try:
                with patch('music_online.catalog', side_effect=slow_catalog):
                    service.handle('online_search', {'query': '', 'page': 1})
                    self.assertTrue(entered.wait(2))
                    self.assertEqual(service.handle('get_state')['job']['state'], 'running')
                    with self.assertRaises(ValueError):
                        service.handle('online_search', {'query': 'second', 'page': 1})
                    service.handle('cancel_job')
                    release.set()
                    service.job_thread.join(3)
                    self.assertEqual(service.job['state'], 'cancelled')
                    self.assertIsNone(service.online_catalog)
                    self.assertFalse(service.library.items)
            finally:
                release.set()
                service.shutdown()

    def test_invalid_download_preserves_existing_library(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MusicService(directory, backend_factory=Mock(), monitor=False)
            try:
                service.handle('add_text', {'title': '保留曲目', 'text': '1 2 3'})
                before = service.library.path.read_bytes()
                with patch('music_online.download', return_value=(b'MThdBAD', '坏文件', '')):
                    service.handle('online_download', {'id': ID})
                    service.job_thread.join(3)
                self.assertEqual(service.job['state'], 'error')
                self.assertEqual(service.library.path.read_bytes(), before)
                self.assertFalse(list((service.library.path.parent / 'online-scores').glob('*.mid')))
            finally:
                service.shutdown()


if __name__ == '__main__':
    unittest.main()
