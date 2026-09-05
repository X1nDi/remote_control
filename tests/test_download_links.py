import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pc_controller.bot_service import TelegramBotService


class DownloadLinkTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'metadata.json'
        self.path.write_bytes(b'x' * 400)
        self.bot = SimpleNamespace(
            _dir_items_by_user={}, _download_listings_by_user={},
            _delete_user_message=AsyncMock(), _ensure_admin=AsyncMock(return_value=True),
            _safe_reply=AsyncMock(), _send_temporary_status=AsyncMock(),
            _delete_message_safe=AsyncMock(), _share_large_file=AsyncMock(),
            _resolve_user_path=Mock(side_effect=lambda uid, path: Path(path)),
            _dismiss_markup=Mock(return_value=None),
            _format_bytes=lambda size: str(size), _get_fast_dir_size=lambda path:(0,False))
        self.chat = SimpleNamespace(send_document=AsyncMock(),send_photo=AsyncMock(),send_video=AsyncMock())
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=7),effective_chat=self.chat)

    def listing(self):
        text,_ = TelegramBotService._build_interactive_dir_page(self.bot,7,self.root,'testbot')
        return re.search(r'start=(dl_[a-f0-9]+_\d+)',text)[1]

    async def start(self,arg):
        await TelegramBotService._command_start(self.bot,self.update,SimpleNamespace(args=[arg]))

    async def test_restart_link_replies_instead_of_silent_return(self):
        arg=self.listing()
        self.bot._download_listings_by_user.clear()
        await self.start(arg)
        self.assertIn('устарела',self.bot._safe_reply.call_args.args[1])
        self.chat.send_document.assert_not_awaited()

    async def test_legacy_index_link_cannot_send_wrong_current_file(self):
        self.listing()
        await self.start('dl_0')
        self.assertIn('устарела',self.bot._safe_reply.call_args.args[1])
        self.chat.send_document.assert_not_awaited()

    async def test_400_byte_file_is_sent_by_start_handler(self):
        await self.start(self.listing())
        self.chat.send_document.assert_awaited_once()
        self.assertEqual(self.chat.send_document.call_args.kwargs['filename'],'metadata.json')
        self.bot._share_large_file.assert_not_awaited()
        self.bot._resolve_user_path.assert_called_once_with(7,str(self.path.resolve()))

    async def test_large_file_start_handler_calls_file_host(self):
        with patch('pc_controller.bot_service.MAX_DOWNLOAD_FILE_SIZE',399):
            await self.start(self.listing())
        self.bot._share_large_file.assert_awaited_once_with(self.update,self.path.resolve())
        self.chat.send_document.assert_not_awaited()

    async def test_refreshed_listing_invalidates_old_link(self):
        old=self.listing(); self.listing()
        await self.start(old)
        self.assertIn('устарела',self.bot._safe_reply.call_args.args[1])
        self.chat.send_document.assert_not_awaited()

    async def test_removed_file_gives_explicit_response(self):
        arg=self.listing(); self.path.unlink()
        await self.start(arg)
        self.assertIn('не существует',self.bot._safe_reply.call_args.args[1])

    async def test_current_permissions_rechecked(self):
        arg=self.listing()
        self.bot._resolve_user_path.side_effect=ValueError('outside allowed root')
        await self.start(arg)
        self.bot._safe_reply.assert_awaited_once()
        self.chat.send_document.assert_not_awaited()
        self.bot._share_large_file.assert_not_awaited()

    async def test_another_user_cannot_use_link(self):
        arg=self.listing(); self.update.effective_user.id=8
        await self.start(arg)
        self.chat.send_document.assert_not_awaited()
        self.assertIn('устарела',self.bot._safe_reply.call_args.args[1])
