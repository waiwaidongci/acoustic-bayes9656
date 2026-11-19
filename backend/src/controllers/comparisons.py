from ..services import compare
class ComparisonsController:
    list=staticmethod(compare.list_comparisons)
    create=staticmethod(compare.create_comparison)
    get=staticmethod(compare.comparison_detail)
    retry=staticmethod(compare.retry_comparison)
    attributions=staticmethod(compare.list_attributions)
    create_attribution=staticmethod(compare.create_attribution)
