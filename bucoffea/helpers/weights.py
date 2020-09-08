import re

import coffea.processor as processor
import numpy as np

from bucoffea.helpers.dataset import extract_year


def get_veto_weights(df, evaluator, electrons, muons, taus, do_variations=False):
    """
    Calculate veto weights for SR W

    The weights are effectively:

        w = product(1-SF)

    where the product runs overveto-able e, mu, tau.
    """
    veto_weights = processor.Weights(size=df.size, storeIndividual=True)

    variations = ["nominal"]
    if do_variations:
        variations.extend([
                      'ele_reco_up','ele_reco_dn',
                      'ele_id_up','ele_id_dn',
                      'muon_id_up','muon_id_dn',
                      'muon_iso_up','muon_iso_dn',
                      'tau_id_up','tau_id_dn'
                      ])

    for variation in variations:
        def varied_weight(sfname, *args):
            '''Helper function to easily get the correct weights for a given variation'''

            # For the nominal variation, just pass through
            if 'nominal' in variation:
                return evaluator[sfname](*args)

            # If this variation is unrelated to the SF at hand,
            # pass through as well
            if not (re.sub('_(up|dn)', '', variation) in sfname):
                return evaluator[sfname](*args)

            # Direction of variation
            sgn = 1 if variation.endswith("up") else -1
            return evaluator[sfname](*args) + sgn * evaluator[f"{sfname}_error"](*args)


        ### Electrons
        if extract_year(df['dataset']) == 2017:
            high_et = electrons.pt>20

            # Low pt SFs
            low_pt_args = (electrons.etasc[~high_et], electrons.pt[~high_et])
            ele_reco_sf_low = varied_weight('ele_reco_pt_lt_20', *low_pt_args)
            ele_id_sf_low = varied_weight("ele_id_loose", *low_pt_args)

            # High pt SFs
            high_pt_args = (electrons.etasc[high_et], electrons.pt[high_et])

            ele_reco_sf_high = varied_weight("ele_reco", *high_pt_args)
            ele_id_sf_high = varied_weight("ele_id_loose", *high_pt_args)

            # Combine
            veto_weight_ele = (1 - ele_reco_sf_low*ele_id_sf_low).prod() * (1-ele_reco_sf_high*ele_id_sf_high).prod()
        else:
            # No split for 2018
            args = (electrons.etasc, electrons.pt)
            ele_reco_sf = varied_weight("ele_reco", *args)
            ele_id_sf = varied_weight("ele_id_loose", *args)

            # Combine
            veto_weight_ele = (1 - ele_id_sf*ele_reco_sf).prod()

        ### Muons
        args = (muons.pt, muons.abseta)
        veto_weight_muo = (1 - varied_weight("muon_id_loose", *args)*varied_weight("muon_iso_loose", *args)).prod()

        ### Taus
        # Taus have their variations saves as separate histograms,
        # so our cool trick from above is replaced by the pedestrian way
        if "tau_id" in variation:
            direction = variation.split("_")[-1]
            tau_sf_name = f"tau_id_{direction}"
        else:
            tau_sf_name = "tau_id"
        veto_weight_tau = (1 - evaluator[tau_sf_name](taus.pt)).prod()

        ### Combine
        total = veto_weight_ele * veto_weight_muo * veto_weight_tau

        # Cap weights just in case
        total[np.abs(total)>5] = 1
        veto_weights.add(variation, total)

    return veto_weights


def diboson_nlo_weights(df, evaluator, gen):

    if re.match(df['dataset'], 'WW_201(6|7|8)'):
        gen_wp = gen[(gen.status==62) & (gen.pdg==24)]
        pt = gen_wp.pt.max()
        w = evaluator['total_nlo_ww_ptwp'][pt]
        dw = evaluator['total_nlo_ww_ptwp_error'][pt]

    elif re.match(df['dataset'], 'WZ_201(6|7|8)'):
        gen_wp = gen[(gen.status==62) & (gen.pdg==24)]
        gen_wm = gen[(gen.status==62) & (gen.pdg==-24)]

        pt1 = gen_wp.pt.max()
        pt2 = gen_wm.pt.max()

        w1 = evaluator['total_nlo_wpz_ptwp']
        w2 = evaluator['total_nlo_wmz_ptwm']
        dw1 = evaluator['total_nlo_wpz_ptwp_error']
        dw2 = evaluator['total_nlo_wmz_ptwm_error']
        pt = np.where(pt1>0,pt1,pt2)
        w = np.where(
            pt1 > 0,
            w1,
            w2
        )
        dw = np.where(
            pt1 > 0,
            dw1,
            dw2
        )
    elif re.match(df['dataset'], 'ZZ_201(6|7|8)'):
        gen_z = gen[(gen.status==62) & (np.abs(gen.pdg)==23)]
        pt = gen_z.pt.max()
        w = evaluator['total_nlo_zz_ptz'][pt]
        dw = evaluator['total_nlo_zz_ptz_error'][pt]
    else:
        w = np.ones(df.size)
        pt = w
        dw = np.zeros(df.size)

    w[pt<0] = 1
    dw[pt<0] = 0

    df['weight_diboson_nlo'] = w
    df['weight_diboson_nlo_rel_unc'] = dw/w
