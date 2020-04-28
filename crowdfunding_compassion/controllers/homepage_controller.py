from datetime import datetime

from odoo.http import request, route, Controller


class HomepageController(Controller):
    @route("/homepage", auth="public", website=True)
    def homepage(self, **kwargs):
        context = {
            "funds": request.env['product.product'].sudo().search([
                ('activate_for_crowdfunding', '=', True)
            ]),
            "impact": self._compute_projects_impact(datetime.now().year),
        }

        return request.render("crowdfunding_compassion.homepage_template", context)

    def _compute_projects_impact(self, year, **kwargs):
        projects = (
            request.env["crowdfunding.project"]
            .sudo()
            .search(
                [
                    ("deadline", ">=", datetime(year, 1, 1)),
                    ("deadline", "<=", datetime(year, 12, 31)),
                ]
            )
        )

        impact = {
            "sponsorship": 0,
            "toilets": 0,
            "csp": 0,
            "other": 0,
        }

        toilets_fund = request.env.ref(
            "sponsorship_switzerland.product_template_fund_toilets"
        )
        csp_fund = request.env.ref("sponsorship_switzerland.product_template_fund_csp")

        for project in projects:
            impact["sponsorship"] += project.number_sponsorships_reached

            if project.product_id == toilets_fund.id:
                impact["toilets"] += project.product_number_reached

            elif project.product_id == csp_fund.id:
                impact["csp"] += project.product_number_reached

            elif project.product_id:
                impact["other"] += project.product_number_reached

        return impact