from product_access.native import NativeProductAccessMixin as _NativeProductAccessMixin
from product_access.production_boundary import ProductionAccessBoundaryMixin


class NativeProductAccessMixin(ProductionAccessBoundaryMixin, _NativeProductAccessMixin):
    """Compose the native license owner with the production publication guard."""

    pass
