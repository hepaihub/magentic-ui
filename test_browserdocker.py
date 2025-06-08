# src/magentic_ui/tools/playwright/browser/base_playwright_browser.py
from src.magentic_ui.tools.playwright.browser.base_playwright_browser import (
    DockerPlaywrightBrowser, PlaywrightBrowser)
from src.magentic_ui.tools.playwright.playwright_controller import PlaywrightController

from pathlib import Path
here = Path(__file__).parent.resolve()

import asyncio

from src.magentic_ui.tools.playwright.browser.utils import get_browser_resource_config



class TestBrowser:
    def __init__(self):
        bind_path = Path(f"{here}/docker_test_dir_{hash(asyncio.get_event_loop().time()) % 10000}")
        browser_resource_config, self.novnc_port, playwright_port = get_browser_resource_config(bind_path, -1, -1, False
            )

        self._browser = PlaywrightBrowser.load_component(browser_resource_config)
        
        # def _download_handler(download: Download) -> None:
        #     self._last_download = download
        
        # self._playwright_controller = PlaywrightController(
        #     animate_actions=True
        #     downloads_folder=f"{bind_path}",
        #     viewport_width=1440,
        #     viewport_height=1440,
        #     _download_handler=self._download_handler,
        #     to_resize_viewport=True,
        #     single_tab_mode=False,
        #     url_status_manager=self._url_status_manager,
        #     url_validation_callback=self._check_url_and_generate_msg,
        # )
        pass
    
    
    async def run(self):
        await self._browser.__aenter__()  # 启动容器
        self._context = self._browser.browser_context
        # Create the page
        assert self._context is not None
        self._context.set_default_timeout(20000)  # 20 sec

        # self._page = None
        # self._page = await self._context.new_page()
        # await self._playwright_controller.on_new_page(self._page)

        # async def handle_new_page(new_pg: Page) -> None:
        #     # last resort on new tabs
        #     assert new_pg is not None
        #     assert self._page is not None
        #     await new_pg.wait_for_load_state("domcontentloaded")
        #     new_url = new_pg.url
        #     await new_pg.close()
        #     await self._playwright_controller.visit_page(self._page, new_url)

        # if self.single_tab_mode:
        #     # this will make sure any new tabs will be closed and redirected to the main page
        #     # it is a last resort, the playwright controller handles most cases
        #     self._context.on("page", lambda new_pg: handle_new_page(new_pg))

        # try:
        #     await self._playwright_controller.visit_page(self._page, self.start_page)
        # except Exception:
        #     pass

        # # Prepare the debug directory -- which stores the screenshots generated throughout the process
        # await self._set_debug_dir()
    
    
        print(f"WebSurfer started with browser at `http://localhost:{self.novnc_port}/vnc.html?autoconnect=true&amp;resize=scale&amp;show_dot=true&amp;scaling=local&amp;quality=7&amp;compression=0&amp;view_only=0`")

if __name__ == "__main__":
    # asyncio.run(main())
    import asyncio
    async def main():
        browser = TestBrowser()
        await browser.run()
    asyncio.run(main())

