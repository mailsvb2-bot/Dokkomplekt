from __future__ import annotations

from window_core_mixin import WindowCoreMixin
from window_style_mixin import WindowStyleMixin
from window_chrome_mixin import WindowChromeMixin
from window_header_mixin import WindowHeaderMixin
from window_universal_dialogs_mixin import WindowUniversalDialogsMixin


class WindowMixin(
    WindowCoreMixin,
    WindowStyleMixin,
    WindowChromeMixin,
    WindowHeaderMixin,
    WindowUniversalDialogsMixin,
):
    """Composed window/UI surface mixin.

    The former monolithic WindowMixin is split into small responsibility-based
    mixins so UI growth does not recreate a god class.
    """
