from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountReconcileModel(models.Model):
    _inherit = 'account.reconcile.model'

    def _get_invoice_matching_rule_result(self, st_line, candidates, aml_ids_to_exclude, reconciled_amls_ids, partner):
        new_reconciled_aml_ids = set()
        new_treated_aml_ids = set()
        candidates, priorities = self._filter_candidates(candidates, aml_ids_to_exclude, reconciled_amls_ids)

        st_line_currency = st_line.foreign_currency_id or st_line.currency_id
        candidate_currencies = set(candidate['aml_currency_id'] for candidate in candidates)
        kept_candidates = candidates
        if candidate_currencies == {st_line_currency.id}:
            kept_candidates = []
            sum_kept_candidates = 0
            for candidate in candidates:
                candidate_residual = candidate['aml_amount_residual_currency']

                if st_line_currency.compare_amounts(candidate_residual, -st_line.amount_residual) == 0:
                    # Special case: the amounts are the same, submit the line directly.
                    kept_candidates = [candidate]
                    break

                elif st_line_currency.compare_amounts(abs(sum_kept_candidates), abs(st_line.amount_residual)) < 0:
                    # Candidates' and statement line's balances have the same sign, thanks to _get_invoice_matching_query.
                    # We hence can compare their absolute value without any issue.
                    # Here, we still have room for other candidates ; so we add the current one to the list we keep.
                    # Then, we continue iterating, even if there is no room anymore, just in case one of the following candidates
                    # is an exact match, which would then be preferred on the current candidates.
                    kept_candidates.append(candidate)
                    sum_kept_candidates += candidate_residual

        # It is possible kept_candidates now contain less different priorities; update them
        kept_candidates_by_priority = self._sort_reconciliation_candidates_by_priority(kept_candidates, aml_ids_to_exclude, reconciled_amls_ids)
        priorities = set(kept_candidates_by_priority.keys())

        # We check the amount criteria of the reconciliation model, and select the
        # kept_candidates if they pass the verification.
        matched_candidates_values = self._process_matched_candidates_data(st_line, kept_candidates)
        status = self._check_rule_propositions(matched_candidates_values)
        if 'rejected' in status:
            rslt = None
        else:
            rslt = {
                'model': self,
                'aml_ids': [candidate['aml_id'] for candidate in kept_candidates],
            }
            new_treated_aml_ids = set(rslt['aml_ids'])

            # Create write-off lines (in company's currency).
            if 'allow_write_off' in status:
                residual_balance_after_rec = matched_candidates_values['residual_balance_curr'] + matched_candidates_values['candidates_balance_curr']
                writeoff_vals_list = self._get_write_off_move_lines_dict(
                    st_line,
                    matched_candidates_values['balance_sign'] * residual_balance_after_rec,
                    partner.id,
                )
                if writeoff_vals_list:
                    rslt['status'] = 'write_off'
                    rslt['write_off_vals'] = writeoff_vals_list
            else:
                writeoff_vals_list = []

            # Reconcile.
            if 'allow_auto_reconcile' in status:

                # Process auto-reconciliation. We only do that for the first two priorities, if they are not matched elsewhere.
                aml_ids = [candidate['aml_id'] for candidate in kept_candidates]
                lines_vals_list = [{'id': aml_id} for aml_id in aml_ids]

                do_reconcile = False

                if len(kept_candidates) == 1 and self.match_partner:
                    if kept_candidates[0]['aml_amount_residual_currency'] == st_line.amount_total:
                        do_reconcile = True

                if lines_vals_list and (priorities & {1, 3} or do_reconcile) and self.auto_reconcile:

                    # Ensure this will not raise an error if case of missing account to create an open balance.
                    dummy, open_balance_vals = st_line._prepare_reconciliation(lines_vals_list + writeoff_vals_list)

                    if not open_balance_vals or open_balance_vals.get('account_id'):

                        if not st_line.partner_id and partner:
                            st_line.partner_id = partner

                        st_line.reconcile(lines_vals_list + writeoff_vals_list, allow_partial=True)

                        rslt['status'] = 'reconciled'
                        rslt['reconciled_lines'] = st_line.line_ids
                        new_reconciled_aml_ids = new_treated_aml_ids

        return rslt, new_reconciled_aml_ids, new_treated_aml_ids