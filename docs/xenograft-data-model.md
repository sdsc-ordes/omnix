## Data model


```json
{  
    "Tumors": [  
      {  
        "slims_id": "TUMOR_00000101",  
        "sample_id": "T-099",
        "omero_link": "http://omero.link"
        #"treatments": "unique(`Treatment`)",  
        #"rna_sequenced": true,  
        #"dna_sequenced": false,  
        #"number_of_experiments": "length(unique(`Mouse exp #`))"  
      }  
    ],  
    "Mouse": [  
      "slims_id": "00012844",  
      "mouse_exp_number": "12",  
      "tumor_id": "T-099",  
      "generation": "G7(5)",  
      "treatment": "tamoxifen (chow)"  
    ],  
    "Assay": [  
      {  
        "assay_type": "Blood sample",  
        "experiment_number": "12",  
        "tumor_id": "T-099",  
        "organ": null  
      },  
      {  
        "assay_type": "Tissue for RNA",  
        "experiment_number": "12",  
        "tumor_id": "T-099",  
        "organ": "3L"  
      }  
    ]  
  }  
```
