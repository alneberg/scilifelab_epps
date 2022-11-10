#!/usr/bin/env python

DESC = """
Each function in this module corresponds to a single method / application and is tied to a
specific workflow step.

Written by Alfred Kedhammar
"""

import zika
import pandas as pd
import sys
import numpy as np


def setup_QIAseq(currentStep, lims):
    """
    Normalize to target amount and volume.

    Cases:
    1) Not enough sample       --> Decrease amount, flag
    2) Enough sample           --> OK
    3) Sample too concentrated --> Maintain target concentration, increase
                                   volume as needed up to max 15 ul, otherwise
                                   throw error and dilute manually.
    """

    # Create dataframe
    to_fetch = [
        # Sample info
        "sample_name",
        "conc",
        "vol",
        "amt",
        # Plates and positions
        "source_fc",
        "source_well",
        "conc_units",
        "dest_fc",
        "dest_well",
        "dest_fc_name",
        # Target info
        "target_vol",
        "target_amt",
    ]
    
    df = zika.fetch_sample_data(currentStep, to_fetch)
    assert all(df.conc_units == "ng/ul"), "All sample concentrations are expected in 'ng/ul'"
    assert all(df.target_amt > 0), "'Amount taken (ng)' needs to be set greater than zero"
    assert all(df.vol > 0), "Sample volume needs to be greater than zero" 

    # Define constraints
    zika_min_vol = 0.1
    well_max_vol = 15

    # Make calculations
    df["target_conc"] = df.target_amt / df.target_vol
    df["min_transfer_amt"] = np.minimum(df.vol, zika_min_vol) * df.conc
    df["max_transfer_amt"] = np.minimum(df.vol, df.target_vol) * df.conc

    # Define deck
    assert len(df.source_fc.unique()) == 1, "Only one input plate allowed"
    assert len(df.dest_fc.unique()) == 1, "Only one output plate allowed"
    deck = {
        "buffer_plate": 2,
        df.source_fc.unique()[0]: 3,
        df.dest_fc.unique()[0]: 4,
    }

    # Load outputs for changing UDF:s
    outputs = {art.name : art for art in currentStep.all_outputs() if art.type == "Analyte"}

    # Cases 1) - 3)
    d = {"sample": [], "buffer": [], "tot_vol": []}
    log = []
    for i, r in df.iterrows():

        # 1) Not enough sample
        if r.max_transfer_amt < r.target_amt:

            sample_vol = min(r.target_vol, r.vol)
            tot_vol = r.target_vol
            buffer_vol = tot_vol - sample_vol

            final_amt = sample_vol * r.conc
            final_conc = final_amt / tot_vol
            
            log.append(
                f"WARNING: Insufficient amount of sample {r.sample_name} (conc {r.conc} ng/ul, vol {r.vol} ul)"
            )
            log.append(f"\t--> Adjusted to {final_amt} ng in {tot_vol} ul ({final_conc} ng/ul)")

            op = outputs[r.sample_name]
            op.udf['Amount taken (ng)'] = final_amt
            op.put()

        # 2) Ideal case
        elif r.min_transfer_amt <= r.target_amt <= r.max_transfer_amt:

            sample_vol = r.target_amt / r.conc
            buffer_vol = r.target_vol - sample_vol
            tot_vol = sample_vol + buffer_vol

        # 3) Sample too concentrated -> Increase final volume if possible
        elif r.min_transfer_amt > r.target_amt:

            increased_vol = r.min_transfer_amt / r.target_conc
            assert (
                increased_vol < well_max_vol
            ), f"Sample {r.name} is too concentrated ({r.conc} ng/ul) and must be diluted manually"

            tot_vol = increased_vol
            sample_vol = zika_min_vol
            buffer_vol = tot_vol - sample_vol

            final_amt = sample_vol * r.conc
            final_conc = final_amt / tot_vol

            log.append(
                f"WARNING: High concentration of sample {r.sample_name} ({r.conc} ng/ul)"
            )
            log.append(f"\t--> Adjusted to {final_amt} in {tot_vol} ul ({final_conc} ng/ul)")
            
            op = outputs[r.sample_name]
            op.udf['Total Volume (uL)'] = tot_vol
            op.put()

        d["sample"].append(sample_vol)
        d["buffer"].append(buffer_vol)
        d["tot_vol"].append(tot_vol)

    df = df.join(pd.DataFrame(d))

    # Resolve buffer transfers
    df = zika.resolve_buffer_transfers(df, buffer_strategy="column")

    # Generate Mosquito-readable columns
    df = zika.format_worklist(df, deck=deck)

    # Comments to attach to the worklist header
    n_samples = len(df[df.src_type == "sample"])
    comments = [f"This worklist will enact normalization of {n_samples} samples"]

    # Write files and upload
    method_name = "setup_QIAseq"
    wl_filename, log_filename = zika.get_filenames(method_name, currentStep.id)

    zika.write_worklist(
        df=df,
        deck=deck,
        wl_filename=wl_filename,
        comments=comments,
        strategy="multi-aspirate",
    )

    zika.upload_log(currentStep, lims, log, log_filename)
    zika.upload_csv(currentStep, lims, wl_filename)

    # Issue warnings, if any
    if any("WARNING:" in entry for entry in log):
        sys.stderr.write(
            "CSV-file generated with warnings, please check the Log file\n"
        )
        sys.exit(2)

    

def amp_norm(currentStep, lims):
    
    # Create dataframe
    
    to_fetch = [
        # Sample info
        "sample_name",
        "user_conc",
        "user_vol",
        # Plates and wells
        "source_fc",
        "source_well",
        "dest_fc",
        "dest_well",
        "dest_fc_name",
        # Target info
        "target_vol",
        "target_amt",
    ]
    
    df = zika.fetch_sample_data(currentStep, to_fetch)
    # Treat user-measured conc/volume as 
    df.rename({"user_conc" : "conc", "user_vol" : "vol"})

    assert all(df.target_amt > 0), "'Amount taken (ng)' needs to be set greater than zero"
    assert all(df.vol > 0), "Sample volume needs to be greater than zero" 

    # Define constraints
    zika_min_vol = 0.1  # Lowest possible transfer volume
    zika_max_vol = 5
    zika_dead_vol = 5   # Estimated dead volume of TwinTec96 wells
    well_max_vol = 180  # Estimated max volume of TwinTec96 wells