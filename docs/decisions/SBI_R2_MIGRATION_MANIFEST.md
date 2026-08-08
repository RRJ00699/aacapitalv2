# SBI R2 migration manifest

**Status: PREPARED — OWNER APPROVAL REQUIRED FOR REAL INGEST**

## Evidence and safety boundary

- **VERIFIED (local):** 241 tracked PDF files, 137,109,346 bytes.
- **UNKNOWN (remote):** documents-ledger, R2-object, IPO-spine, `source_facts`, and `insights` coverage. No production credentials were used and no API call or write was made.
- **VERIFIED (implementation):** `python pipeline/sbi_migration_verify.py --dry-run` hashes local bytes only. Remote verification is separately gated by both `--owner-approved` and `SBI_OWNER_APPROVED=YES`.
- **INFERENCE:** filenames containing `IPO Note` identify an IPO/company candidate only; they do not prove canonical IPO ownership. The resolver must prove exact ISIN or canonical `name_norm` before ingest.

Because remote coverage and canonical IPO resolution were not queried, the table does **not** claim any file is ledgered, R2-verified, extracted, or deletion-ready. `READY_FOR_INGEST` means only that the local PDF is hashable and can enter the owner-gated resolver; it is not permission to upload.

## Cost checkpoint before any real run

- Notes: 241
- Requiring upload: **UNKNOWN** (maximum 241)
- Already in R2: **UNKNOWN**
- Requiring Sonnet: **UNKNOWN** (maximum 241)
- Estimated R2 operations: up to 241 HEAD + 241 PUT + 241 post-PUT HEAD; GET only where SHA metadata cannot prove bytes.
- Estimated Neon activity: approximately 241 identity reads + 241 ledger reads; up to 241 ledger inserts/metadata fills plus claim writes. Exact write count depends on extraction output.
- Estimated Sonnet tokens/note and USD cost: **UNKNOWN until page/text token inventory is produced; no paid call is authorized.**
- Estimated runtime: **UNKNOWN until remote latency and token inventory are known.**

## Local inventory

| # | Filename / detected reference | Bytes | SHA256 | Ledger | Object key / R2 | Existing SBI facts | Classification |
|---:|---|---:|---|---|---|---|---|
| 1 | `ACME Solar Holdings Ltd_IPO Note.pdf`<br>ACME Solar Holdings Ltd | 430,261 | `f99d8432fc50e38e7deaebb8dfcda4a317ae397f2f780c1c4b88a7ae30d98096` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 2 | `ASK Automotive Limited_IPO Note.pdf`<br>ASK Automotive Limited | 427,353 | `8000af67201a9c4e9279565212e2e21e80930b0e5eab69827e60d5e9b163ffe9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 3 | `Aadhar Housing Finance Limited_IPO Note.pdf`<br>Aadhar Housing Finance Limited | 605,780 | `b1c7b9b50599abd3091c1dce2e8ae32ae53289799271458f4a8a06b7cbff7b10` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 4 | `Aastha Spintex Ltd_IPO Note.pdf`<br>Aastha Spintex Ltd | 366,070 | `54a92a1dd47c4696118080f6f76d5991888c65eaa916e6345d10156b4e2f5310` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 5 | `Aditya Infotech Ltd_IPO Note.pdf`<br>Aditya Infotech Ltd | 655,485 | `15ff042cae49e472a16cafc3f0f66068df3069fcdcca373f2735cf318830da35` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 6 | `Advance Agrolife Limited_IPO Note.pdf`<br>Advance Agrolife Limited | 393,536 | `8c99dd8daf4b0a6bd7de4775d69a8dfed5452999f816548233b1d7d6d85fee9a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 7 | `Advit Jewels Ltd_IPO Note.pdf`<br>Advit Jewels Ltd | 298,716 | `824722eaf7cd47b7424b5d6dd43f0504263818d919c2534e372320cc0a1ee7ee` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 8 | `Aegis Vopak Terminals Ltd_IPO Note.pdf`<br>Aegis Vopak Terminals Ltd | 561,564 | `8ec7b90bc0a05ae8d45b11c7fe2296a9b77754cc0ea5258d7ad270afe0d365a3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 9 | `Aequs Ltd_IPO Note.pdf`<br>Aequs Ltd | 816,641 | `387d8a8eeb335db36ff440cd77677d8712cae8ab9cc024f0c3341bca17417175` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 10 | `Aeroflex Industries Limited_IPO Note.pdf`<br>Aeroflex Industries Limited | 455,334 | `ed6c7a280df39f1523f9fa09e813bfe551192e6b50f669c49f0344f34e4db870` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 11 | `Afcons Infrastructure Ltd_IPO Note.pdf`<br>Afcons Infrastructure Ltd | 533,844 | `8b2ac4d38c589db8e76690cad54ccc257a9dcd0f9e589a6e89cbd82c67b9f6c7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 12 | `Ajax Engineering Ltd_IPO Note.pdf`<br>Ajax Engineering Ltd | 526,344 | `ac5ed0f7f0573c9bcbd52556661c5bbca2bd1e28cb66fac168c1fc6a29732574` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 13 | `Akums Drugs and Pharmaceuticals Limited_IPO Note.pdf`<br>Akums Drugs and Pharmaceuticals Limited | 459,694 | `1f983ac36d22b4cf3fe28cece50f943993a001414d4dfb9db16f5f62c3f1a933` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 14 | `All Time Plastics Ltd_IPO Note.pdf`<br>All Time Plastics Ltd | 554,912 | `77351359050d7edac6a311bfbfed72de81608dccdf86b9e2de69dad1927f3070` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 15 | `Allied Blenders _ Distillers Ltd_IPO Note.pdf`<br>Allied Blenders _ Distillers Ltd | 492,143 | `1602a5b2e95c6acad0c4077553904b039a1c76dd5d3570cb91b5a8cae18dba54` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 16 | `Amagi Media Labs Ltd_IPO Note.pdf`<br>Amagi Media Labs Ltd | 893,222 | `ad9d2343889eb92acd83d28e4470255e99f0e6ef0d0b8706e37dbf8740596916` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 17 | `Amir Chand Jagdish Kumar _Exports_ Ltd_IPO Note.pdf`<br>Amir Chand Jagdish Kumar _Exports_ Ltd | 832,817 | `ec5e4863941f85d589a0a4fadf487eaa1e8a7ce0f165b593660d28168ccf13b8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 18 | `Anand Rathi Share _ Stock Brokers Ltd_IPO Note.pdf`<br>Anand Rathi Share _ Stock Brokers Ltd | 481,113 | `ae4cb22ec807850907ec4cab4709f9d6810feb818006ead1d10610457f6cf7de` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 19 | `Anthem Biosciences Ltd_IPO Note.pdf`<br>Anthem Biosciences Ltd | 747,424 | `63120d08f29667475db829028ae7af872781c1c0933ebd3a16920909ad62c7c9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 20 | `Apeejay Surrendra Park Hotels Limited_IPO Note.pdf`<br>Apeejay Surrendra Park Hotels Limited | 526,607 | `5f887bd7b631ff7d9e186d82249b9ed04fca035c5a82a1aa29834075c8829fc9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 21 | `Arisinfra Solutions Ltd._IPO Note.pdf`<br>Arisinfra Solutions Ltd. | 568,349 | `40729103a732c1e4b4e0152c058266a0a00cf0cff7b3cba40c0e2390c7d8b161` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 22 | `Arkade Developers Limited_IPO Note.pdf`<br>Arkade Developers Limited | 535,808 | `cdb195c49871aed618119a6183a4955f2a1a9b3877280e5d56a80cd67c714284` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 23 | `Ather Energy Ltd_IPO Note.pdf`<br>Ather Energy Ltd | 4,428,336 | `eb6cbd43f9f297572499fe379851c5a5c82341c1167f65a20202cb6c27229cf3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 24 | `Atlanta Electricals Ltd_IPO Note.pdf`<br>Atlanta Electricals Ltd | 512,442 | `eb141a0922c8f321f9553967a5c6b577937524bc583fb46aef67a06fd8cdaba9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 25 | `Avalon Technologies Ltd_IPO Note_03-04-2023.pdf`<br>Avalon Technologies Ltd | 459,467 | `e120bbe60b9a08de24be5693dfdb1a0852164db9fa4b0d189bf40bb5f37ce674` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 26 | `Awfis Space Solutions Limited_IPO Note.pdf`<br>Awfis Space Solutions Limited | 785,757 | `b9421c1313a041e705cca268ce3b403022c79c99f52ec3a2305120af1cdfd642` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 27 | `Aye Finance Ltd_IPO Note.pdf`<br>Aye Finance Ltd | 658,203 | `0cdc3d71e6b6266d0ee8336adcfba4733b98c2512b515fb7eb8a8170667f458f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 28 | `Azad Engineering Limited_IPO Note.pdf`<br>Azad Engineering Limited | 502,151 | `cb0cb6f9026866d0b9150a5af5b7cb1584b5e2b94dbe0bb53fd610f662277ba6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 29 | `BMW Ventures Ltd_IPO Note.pdf`<br>BMW Ventures Ltd | 387,338 | `99da0c3d40b55d6896fe9ab81c13e4252846ff2bfd93abb6f7561192113d2ff4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 30 | `Baazar Style Retail Limited_IPO Note.pdf`<br>Baazar Style Retail Limited | 468,347 | `dd39b9a581ff168a5b089cdc66400c2d210ab976bb9655fcc8b4ea3a9fb5c214` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 31 | `Bagmane Prime Office REIT _IPO Note.pdf`<br>Bagmane Prime Office REIT  | 869,800 | `01be62a928d795fd5c2724ade77903b12c9c365e5ccb1f6bf540d2f56baf947c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 32 | `Bajaj Housing Finance Ltd_IPO Note.pdf`<br>Bajaj Housing Finance Ltd | 532,350 | `36465ee0916e6c4bfbe57b08ef95efd15ac35dc0a3c55f0a3c9523b59d5dd502` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 33 | `Bansal Wire Engineering IPO Limited_IPO Note.PDF`<br>Bansal Wire Engineering IPO Limited | 484,870 | `cb5b5db748a93c376c0da69746e3f96d7543f2e0bb3e788c11142fa7559817bb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 34 | `Belrise Industries Limited_IPO Note.pdf`<br>Belrise Industries Limited | 619,628 | `7490288a9b38c03dddb88cbabee5e9ae960b390059e20a8b0e5944934e4f10d8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 35 | `Bharat Coking Coal Ltd_IPO Note.pdf`<br>Bharat Coking Coal Ltd | 748,903 | `26e524c7f787812e9760b017e63185c322dad6e5a838cf60cf2bba951bd96e1a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 36 | `Bharati Hexacom Limited_IPO Note.pdf`<br>Bharati Hexacom Limited | 424,982 | `8af971d264543949dd3cbe77661e80aa8a512b49671d046903330ef90f0105b3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 37 | `Billionbrains Garage Ventures Ltd_IPO Note.pdf`<br>Billionbrains Garage Ventures Ltd | 1,217,383 | `d8cd128a3e1f302099f8d283fc8ceff5b5cf274345154352828c3c41a9238335` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 38 | `Blue Jet Healthcare Limited_IPO Note.pdf`<br>Blue Jet Healthcare Limited | 412,003 | `a876aa4716e887965c057cddfd04ec5c6ca4bd9e0b697711c9caab9593f1db2f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 39 | `BlueStone Jewellery _ Lifestyle Ltd_IPO Note.pdf`<br>BlueStone Jewellery _ Lifestyle Ltd | 656,945 | `48165cf4de7a70b4f672e45738fddc02bfe054558a73a0fc680193ac71e67a85` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 40 | `Borana Weaves Ltd_IPO Note.pdf`<br>Borana Weaves Ltd | 387,038 | `b342eded47ac88edb448227a34b7149431ea8d8391385791dc3a8d677f40bf46` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 41 | `Brainbees Solutions Limited_IPO Note.pdf`<br>Brainbees Solutions Limited | 528,710 | `0ad92f8740c3ce42fc16f3a62396209ee62a6ff6ee0fa8109a716dd417c36ee8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 42 | `Brigade Hotel Ventures Ltd._IPO Note.pdf`<br>Brigade Hotel Ventures Ltd. | 493,893 | `5ad6a60b150f945f4a87a336649308f555818d43cbb4eb24952608bb47786cc2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 43 | `CMR Green Technologies Ltd_IPO Note.pdf`<br>CMR Green Technologies Ltd | 554,351 | `1fed2975cf115f594c249003ded733bba6dee3f8032bbde2e6464f1f5992595c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 44 | `CSM Technologies Ltd._ IPO Note.pdf`<br>CSM Technologies Ltd._ IPO Note | 429,580 | `9116ddf9f9746c905457bebb3052349aeb3debc901cbd3f7b5d45e3199f83e73` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 45 | `Canara HSBC Life Insurance Company Ltd_IPO Note.pdf`<br>Canara HSBC Life Insurance Company Ltd | 567,547 | `11638dfe33cac58fe82fadca2b8dc6199d0057785491661701067aea75c75121` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 46 | `Canara Robeco Asset Management Company Limited_IPO Note.pdf`<br>Canara Robeco Asset Management Company Limited | 525,143 | `2ccd24f79dc035fa4f2ecc9005048fb542b3619766e9bc00371fada708e41997` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 47 | `Capillary Technologies Ltd_IPO Note.pdf`<br>Capillary Technologies Ltd | 846,173 | `19e989ed117fc938c62d53a3f1bb0dcc0aab1269ab82691077938a36abdb9ffe` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 48 | `Carraro India  Limited_IPO Note.PDF`<br>Carraro India  Limited | 633,033 | `f09a69c40e893e1d8dc0907c1714443c5a151943d6e37ad4f444080c6dc6fdef` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 49 | `Ceigall India Ltd_IPO Note.pdf`<br>Ceigall India Ltd | 440,708 | `23aa9576db6f1e97bb8d2d9cc83038e4e0cd5b52dbbda4dd2dab3de923cf8105` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 50 | `Cello World Limited_IPO Note.pdf`<br>Cello World Limited | 529,492 | `591b277575abd44d89deabe774ec4052a77a6308b56304bebf1272a414c7166a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 51 | `Central Mine Planning _ Design Institute Ltd_IPO Note.pdf`<br>Central Mine Planning _ Design Institute Ltd | 644,931 | `13637fd8560b0d72fdc2914b5a4bd27f4b86e25faeaac335873e351fd2cb7046` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 52 | `Clean Max Enviro Energy Solutions Ltd_IPO Note.pdf`<br>Clean Max Enviro Energy Solutions Ltd | 694,319 | `c28c2609fb0cdb9039c4082d3c06d060b06ac5e7ce9880ae1621d5551ce222d6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 53 | `Concord Biotech limited_IPO Note_04-08-2023.pdf`<br>Concord Biotech limited | 435,676 | `5f45c78c78f09750782d2b64b87e1217744ae2b731dc13367317d7199b1f064f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 54 | `Concord Enviro Systems Ltd_IPO Note.pdf`<br>Concord Enviro Systems Ltd | 511,404 | `f4a30511e5ebcfe1f2c80e973c9c225d927cea82ce2e26ca6bc1e07b4bafc54f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 55 | `Cookies-Policy.pdf`<br>Cookies-Policy | 138,141 | `a79b9099b68c6aa453a97b8441decc19db21e18d6e4aa88aa2ffc29f58f1e720` | UNKNOWN | UNKNOWN | UNKNOWN | IPO_RESOLUTION_MISSING |
| 56 | `Corona Remedies Ltd_IPO Note.pdf`<br>Corona Remedies Ltd | 527,124 | `645aedbb8cbc2e1ba51b1b15de44824d0e910d40608c0e6afe512ab4ccf78083` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 57 | `Credo Brands Marketing Limited_IPO Note.pdf`<br>Credo Brands Marketing Limited | 467,101 | `cbebdb864461f68c3837c0c9db5f1215beaa62679d17f9ab177fd732b30383d0` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 58 | `Crizac Ltd_IPO Note.pdf`<br>Crizac Ltd | 523,671 | `1c43ece9860815e36f2f5d02c5b409438a75c4fd73d0bf1ba0c4d652b13a67f4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 59 | `Cyient DLM Limited_IPO NOTE_27-06-2023.pdf`<br>Cyient DLM Limited | 480,774 | `165a0e7514d3ff064e5608d4eb0174f2955dbf31da598727264dca1d8bf61cc1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 60 | `DAM Capital Advisors Ltd_IPO Note.pdf`<br>DAM Capital Advisors Ltd | 447,123 | `526be551376a3c507b2e039d34df766b67946d0025b08bb7dc744c7e9575c1e1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 61 | `DEE Development Engineers Limited_IPO Note.pdf`<br>DEE Development Engineers Limited | 481,328 | `61658d59edae10a92deb8628923c82f931e636ef4cbc8e37054ce74990f81501` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 62 | `DND_20Policy.pdf`<br>DND_20Policy | 172,330 | `6e18ed16b7e7d802c9924e257d4daca32f4fdeb38c4399c9791a076229447bdd` | UNKNOWN | UNKNOWN | UNKNOWN | IPO_RESOLUTION_MISSING |
| 63 | `DOMS Industries Limited_IPO Note.pdf`<br>DOMS Industries Limited | 514,221 | `df6a5cd9534ccd88fe8bdd8913cdd2af466052d34a096bd4cca067e6c0c18548` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 64 | `Denta Water and Infra Solutions Ltd_IPO Note.pdf`<br>Denta Water and Infra Solutions Ltd | 383,306 | `eefc2761e970941a4118f385084ca5595dbf1a043ed807acca743cb95a8a8849` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 65 | `Dev Accelerator Limited_IPO Note.pdf`<br>Dev Accelerator Limited | 395,294 | `c4b334b7f719d7093031750744757f5e6f89f3d83631a7e2ba18189b4daa6b01` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 66 | `Divgi TorqTransfer Systems Ltd_IPO Note-01-03-2023.pdf`<br>Divgi TorqTransfer Systems Ltd | 492,119 | `8be4e0306e524cf802a848d4fb607cb6d8df37540ff018eb48a7b57fc16d26d6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 67 | `Dr. Agarwal_s Health Care Ltd_IPO Note.pdf`<br>Dr. Agarwal_s Health Care Ltd | 529,920 | `5245fc6957355fc42955526dc192911148139e7dae3f6de33d4ae87af9f5854c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 68 | `ECOS _India_ Mobility _ Hospitality Limited_IPO Note.pdf`<br>ECOS _India_ Mobility _ Hospitality Limited | 420,990 | `e13ed95e10df4b51081fce3b6056bc6d7fc785af4131b249d181da8ef477e889` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 69 | `EPACK Durable Limited_IPO Note.pdf`<br>EPACK Durable Limited | 460,032 | `3400f7d9fa60d1d0a66610e70751ba212adfd779eac86ee1743586c82958dd55` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 70 | `ESAF Small Finance Bank Limited_IPO Note.pdf`<br>ESAF Small Finance Bank Limited | 473,497 | `256f85eeb18ce397c508520a59c1fa5d56e906102f1b01d0814eaac7b214403d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 71 | `Ellenbarrie Industrial Gases Ltd_IPO Note.pdf`<br>Ellenbarrie Industrial Gases Ltd | 666,687 | `50b37bd2e82981d0cb2ee8e401de63d1508bf42d54628d396369c755e5eb0856` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 72 | `Emcure Pharmaceuticals Limited_IPO Note.pdf`<br>Emcure Pharmaceuticals Limited | 469,082 | `36e4613a727dd03d2fa18dec49235cd9df6e67f3d36d3fcbb5aea8cf858fe9d1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 73 | `Emmvee Photovoltaic Power Ltd_IPO Note.pdf`<br>Emmvee Photovoltaic Power Ltd | 821,286 | `525bbce2dfeb0d28dc35fd02c4981332d141dc3b4f540e43ee0c5da4e8fea164` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 74 | `Entero Healthcare Solutions Limited_IPO Note.pdf`<br>Entero Healthcare Solutions Limited | 477,657 | `ad244ce0bbfabeae1a527d35f3fe02847faaf4dc86931993f1c79f5f0b519f7a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 75 | `Enviro Infra Engineers Limited_IPO Note.pdf`<br>Enviro Infra Engineers Limited | 493,757 | `0c891fc770e21d2fa459e70bae175642b962380b04ad03ec6aa8be7e374d28c7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 76 | `Epack Prefab Technologies Ltd_IPO Note.pdf`<br>Epack Prefab Technologies Ltd | 657,090 | `dfac1b7371b88a83e1095718cddbcaa67966478451aed0f0e1eee752472244f5` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 77 | `Euro Pratik Sales Limited_IPO Note.pdf`<br>Euro Pratik Sales Limited | 505,449 | `78595a93f940e0da4d0221d67a36b3bf620699ebddfdc344aaa296c41668a0c3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 78 | `Excelsoft Technologies Ltd_IPO Note.pdf`<br>Excelsoft Technologies Ltd | 627,068 | `2f91e5bed642dd56424e813d4e5d212be79b36d157b9d63fb7308d61e608232b` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 79 | `Exicom Tele-Systems Limited_IPO Note.pdf`<br>Exicom Tele-Systems Limited | 456,490 | `81df3034442e4e8fbda2ad4b262569175747deeb9c555c221b902f79a2df9350` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 80 | `Fabtech Technologies Limited_IPO Note.pdf`<br>Fabtech Technologies Limited | 385,930 | `ad89edb262cbf028da8df922d015298776eaf36310f07d27716224fd1c24f3d3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 81 | `Fedbank Financial Services Limited_IPO Note.pdf`<br>Fedbank Financial Services Limited | 442,618 | `5db08d5c7f1e662c1a13d8dd07faf70efa2d668169d99b950f74aec65e7279c6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 82 | `Flair Writing Industries Limited_IPO Note.pdf`<br>Flair Writing Industries Limited | 503,020 | `56121f2528c653f20a7e8397e5ce47a79fd32f0e8325fa72d66df3f1b84875dd` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 83 | `Fractal Analytics Ltd_IPO Note.pdf`<br>Fractal Analytics Ltd | 642,225 | `286911f34f58420be798496db33c9de8f63a1d9830041e8e44d4fc44358ad9fb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 84 | `Fujiyama Power Systems Ltd_IPO Note.pdf`<br>Fujiyama Power Systems Ltd | 778,348 | `de29f912950c8915ae7a1807c11222a27d11b685b238149f0c403c2516e44326` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 85 | `GK Energy Ltd_IPO Note.pdf`<br>GK Energy Ltd | 523,142 | `9ff76e8654957ce657f9dad19315c01b9f88dc042b1322238dd9cea0ce299b37` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 86 | `GNG Electronics Ltd_IPO Note.pdf`<br>GNG Electronics Ltd | 525,136 | `7ce1f595d9b5611befb4554aa0090a31ae8f6965f2471aefb46e0459ec8421a7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 87 | `GPT Healthcare Limited_IPO Note.pdf`<br>GPT Healthcare Limited | 507,081 | `351e361ffc06f71454449bd5575d8e4820eaa6b4b810eb54eaa6b1ec287dbce0` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 88 | `GSP Crop Science Ltd_IPO Note.pdf`<br>GSP Crop Science Ltd | 670,490 | `2ddaeecc78da9e31f49d6b49b143cbe40d005f918da27290c61a23efdf1860d8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 89 | `Gandhar Oil Refinery India Limited_IPO Note.pdf`<br>Gandhar Oil Refinery India Limited | 474,422 | `0b9b9ace5d2379776ee74f2148ad0d8432ed9d7bc3dc599936a469497f7d5814` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 90 | `Ganesh Consumer Products Ltd_IPO Note.pdf`<br>Ganesh Consumer Products Ltd | 555,124 | `d961b95edac5c0ef41fe2bf030b3f7731344d95618694f02ffd9801a73043295` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 91 | `Gem Aromatics Ltd_IPO Note.pdf`<br>Gem Aromatics Ltd | 848,877 | `141011eb1af1b5c0826d22bb2ba12fa01edf88b81bacd9851a68f4e9e12afe56` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 92 | `Globe Civil Projects Ltd_IPO Note.pdf`<br>Globe Civil Projects Ltd | 419,663 | `a022cb1f3ee1908b0370d4437d9a163fbb5b6991c4e702c6361fd9428ac696cb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 93 | `Glottis Ltd_IPO Note.pdf`<br>Glottis Ltd | 731,590 | `6b176de98fab67a14377bedf24a8588b49b7a400bd2c02f6bdd2924a4c22c28f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 94 | `Go Digit General Insurance Limited_IPO Note.pdf`<br>Go Digit General Insurance Limited | 505,914 | `fbd4b9a50f34535e9bcabf0cfadc52137617a081d9acad6b8d380029395993e2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 95 | `Godavari Biorefineries Ltd_IPO Note.pdf`<br>Godavari Biorefineries Ltd | 499,155 | `bfadb40ec9600fe6c70cb7fb7dce63a625ec516813080012117cdda08f6a4267` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 96 | `Gopal Snacks Limited_IPO Note.PDF`<br>Gopal Snacks Limited | 429,107 | `9fe6c0e3603b5d962d83d0c7e24ab02c9303500df28b411d67037a2bca5358fb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 97 | `Gujarat Kidney _ Super Speciality Ltd.pdf`<br>Gujarat Kidney _ Super Speciality Ltd | 380,217 | `07cb681f656ceea424009df7b4ea537c381158a6b6fc1fc98e4bf60ec9060dba` | UNKNOWN | UNKNOWN | UNKNOWN | IPO_RESOLUTION_MISSING |
| 98 | `HDB Financial Services Ltd_IPO Note.pdf`<br>HDB Financial Services Ltd | 442,428 | `eb9f45308a1e712bdacc4d7b0f8f32867ecfc8e66d3314dcb4f17bb9af7a51b6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 99 | `Happy Forgings Limited_IPO Note.pdf`<br>Happy Forgings Limited | 491,919 | `f00e488b48b395175e6cccf329d3619638a19160caa09fec694b27a83470ee38` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 100 | `Hexagon Nutrition_IPO Note.pdf`<br>Hexagon Nutrition | 379,101 | `c10c31c9a908304baad32922e7764ee12b7eeb9dcb511a50972617cdfaf0e2df` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 101 | `Hexaware Technologies Ltd_IPO Note.pdf`<br>Hexaware Technologies Ltd | 508,253 | `2c4a827dfd7a80774202c1288b795f889bb7f5c4bc5bd15e7a24024e768fb74d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 102 | `Highway Infrastructure Limited_IPO Note.pdf`<br>Highway Infrastructure Limited | 408,765 | `ce3412f7be3fc81ee354ed4ff8b66aec1d13c27bb54318a69a5693bf53c3d68a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 103 | `Hyundai Motor India Ltd_IPO Note.pdf`<br>Hyundai Motor India Ltd | 480,388 | `f6c903295113e239df9ae272613055ec491df7453a4a0bb897ccc63fd454aa02` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 104 | `ICICI Prudential Asset Management Company Limited_IPO Note.pdf`<br>ICICI Prudential Asset Management Company Limited | 509,893 | `d848f3198ae19352a32f05a1296725aeb0ccb203a77fa4d00af7c4314c046e9f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 105 | `IKIO Lighting Limited_IPO NOTE_05-06-2023.pdf`<br>IKIO Lighting Limited | 521,960 | `945cc2de3ca29741d6950f192fd798c310d17ba9cc7898a0cd87b4a7907012b5` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 106 | `INOX India Limited_IPO Note.pdf`<br>INOX India Limited | 441,568 | `f8a3e4b0242d31ed305371e25a605d9994529ff45700da36eb07685eb33a75a8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 107 | `IRDAI_20Public_20notice.pdf`<br>IRDAI_20Public_20notice | 117,893 | `6dd7a7cb25c530da8594fb59e0421e4fb684fc1724533ce404fb19441fcfb3d6` | UNKNOWN | UNKNOWN | UNKNOWN | IPO_RESOLUTION_MISSING |
| 108 | `IRM Energy Limited_IPO Note.pdf`<br>IRM Energy Limited | 675,063 | `a027b0a1574c69a3794aa2e34611d0743de111f1414e2e24db059d151000b2af` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 109 | `Indegene Limited_IPO Note.pdf`<br>Indegene Limited | 445,559 | `0a66b2bcd99cda452e728c7bb1ba5d7a33d414a39c7e400eca4958cf95a0071f` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 110 | `India Shelter Finance Corporation Limited_IPO Note.pdf`<br>India Shelter Finance Corporation Limited | 400,893 | `2b4f09641f46d743a413f26be498b7f4e5c4e03398b4b146cb21ed0db82161d9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 111 | `Indian Renewable Energy Development Agency Limited_IPO Note.pdf`<br>Indian Renewable Energy Development Agency Limited | 609,411 | `1fed590129e56f6b688ff5107fcef146c3f8a24a56d20cea2b91c5cd01a7c0d2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 112 | `Indiqube Spaces Limited_IPO Note.pdf`<br>Indiqube Spaces Limited | 801,972 | `9ee91809ae20b0681d2f38111dbb8f43ace8f63146a1532b29ef76dda7183353` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 113 | `Indo Farm Equipment Ltd_IPO Note.pdf`<br>Indo Farm Equipment Ltd | 495,814 | `d4ac1e04536f04367462008c237b7cf8f03a7dc59668d93eb48d302aae8b7147` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 114 | `Indogulf Cropsciences Ltd_IPO Note.pdf`<br>Indogulf Cropsciences Ltd | 409,085 | `02483f18da026c7677fbaf2cde35a4beace5c0142a2dd11916174398c697e653` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 115 | `Innova Captab Limited_IPO Note.pdf`<br>Innova Captab Limited | 488,578 | `9aa4fc28ea18f9caa8fc8a49b81511c55d973a92cfd30a52ec3f1caed9d77005` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 116 | `Innovision_IPO Note.pdf`<br>Innovision | 502,917 | `cf520978ffa3c9a9d70f930e7fad39146732a45cdf7aca65987dbdf2c04354e1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 117 | `Interarch Building Products Limited_IPO Note.PDF`<br>Interarch Building Products Limited | 453,551 | `8755d5140b5b86c7a8efcdc136767883cd7fab2eb1e259f9c1d9f952eccea208` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 118 | `International Gemmological Institute _India_ Ltd_IPO Note.pdf`<br>International Gemmological Institute _India_ Ltd | 624,125 | `71dcd2fe81c4e3a7e9e60b9f72bb1880f28ce796239f546ebff56d8b931ff79a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 119 | `Inventurus Knowledge Solutions Ltd_IPO Note.pdf`<br>Inventurus Knowledge Solutions Ltd | 429,859 | `bde49a107e4711bcfd1c6988460f5609ab6bbbf0c64168b24ecfe1be140428b2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 120 | `JNK India Ltd_IPO Notes.pdf`<br>JNK India Ltd | 471,175 | `43e2ac6af2e5df703f8591d7bfe2f41cb70004b3e08c03e6dd2ec4268c54a553` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 121 | `JSW Cement Ltd_IPO Note.pdf`<br>JSW Cement Ltd | 728,208 | `0f0ec81f8aa817e5747488e7806be7df9dd0dafae311bea7fd8aac699e7e01e6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 122 | `JSW Infrastructure Limited_IPO Note.pdf`<br>JSW Infrastructure Limited | 457,428 | `6a5a33bc5a46925e03c15278be1b5960e9c0f6492ea166b8c8b9e4b4aa991c7d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 123 | `Jain Resource Recycling Ltd_IPO Note.pdf`<br>Jain Resource Recycling Ltd | 506,432 | `2cfaf7618a754905f2abf63e14a4344ee8e86a071cca0b3c1684b704934caaf2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 124 | `Jaro Institute of Technology Management _ Research Ltd_IPO Note.pdf`<br>Jaro Institute of Technology Management _ Research Ltd | 479,577 | `8d5724e28050f6fd2aabf62e0fc087008218a8239c75ff8fbc7361607f1f60a6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 125 | `Juniper Hotels Limited_IPO Note.pdf`<br>Juniper Hotels Limited | 593,650 | `41d46b3fae30a41076520472bfb5568f396f0852f377c9ab6463f3c0fd5f33f1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 126 | `Jupiter Life Line Hospital Limited_IPO Note.pdf`<br>Jupiter Life Line Hospital Limited | 454,974 | `ba1cc4ba11c90aab62332facf362ae59c848d77bdcd620e8537c0dcde38f3458` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 127 | `Jyoti CNC Automation Limited_IPO Note.pdf`<br>Jyoti CNC Automation Limited | 477,379 | `92b94efdefa657a490940115e488dcc46f330b2d0950c9a86cf50e063413d77c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 128 | `KRN Heat Exchanger _ Refrigeration Ltd_IPO Note.pdf`<br>KRN Heat Exchanger _ Refrigeration Ltd | 455,537 | `aca11c444cd0094df4407ff83961d113a8775641cc0e2df80f4fa4f0fdfa89b4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 129 | `KSH International Ltd_IPO Note.pdf`<br>KSH International Ltd | 617,607 | `0316e677dad9e04bd78dec9486aeccc7fecc7b13c806e3cbc47e861f32abb7ee` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 130 | `Kalpataru Ltd_IPO Note.pdf`<br>Kalpataru Ltd | 715,872 | `2378564ebad38aedd333167d85d90db9912cffa3e2d2cf43d76fe5ac4604e50b` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 131 | `Knack Packaging_IPO Note.pdf`<br>Knack Packaging | 728,770 | `45c376cc2116c227b1fc396138dba147ab27c919129210de364da6a754a64a0d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 132 | `Knowledge Realty Trust_IPO Note.pdf`<br>Knowledge Realty Trust | 592,004 | `6bc575a66fbec07a9689da7d2b38e5cd14eb9ddf7204f6842503964afe603661` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 133 | `Kross Limited_IPO Note.pdf`<br>Kross Limited | 430,700 | `655e01383e96b410f4da7d70b8044565b0220306a810e20cfb03e0cf2892b5e2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 134 | `LG Electronics India Ltd_IPO Note.pdf`<br>LG Electronics India Ltd | 634,734 | `413feb49508b82c0f9d791f5fb26a9f51221f69cab3df7de9e2542d4eb7525a4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 135 | `Laxmi Dental Ltd_IPO Note.pdf`<br>Laxmi Dental Ltd | 506,945 | `51ea343e49a33b6f9eb1441b4ea0ce1d9684d5e92fe20d94ae3bcb387df21c8e` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 136 | `Laxmi India Finance_IPO Note.pdf`<br>Laxmi India Finance | 390,355 | `1897598902b6dd5aa72bf78b8f700091c180f1ba1a1acdb76fb23ef8c5d294a6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 137 | `Le Travenues Technology Limited_IPO Note.pdf`<br>Le Travenues Technology Limited | 447,620 | `0d049681fbe24de967b4be0e4e3f0fd8a42edba4b4fb6598825ca781ff4c1ca9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 138 | `Lenskart Solutions Ltd_IPO Note.pdf`<br>Lenskart Solutions Ltd | 779,307 | `35ab2641b3cf0fffd262081d45d48132b21e8b1f6a1708df2a8b77aba5746e83` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 139 | `M_B Engineering Ltd_IPO Note.pdf`<br>M_B Engineering Ltd | 608,370 | `a1123399896396002b195c09f5d3196e6edf329171677da866e6f11a81a47406` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 140 | `Mangal Electrical Industries Ltd_IPO Note.pdf`<br>Mangal Electrical Industries Ltd | 543,178 | `b04ebfcba1fb6ee7451ad7a78a20d1784567fc56a605b544cc8a538950d88f82` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 141 | `Mankind Pharma Ltd_ IPO Note.pdf`<br>Mankind Pharma Ltd_ IPO Note | 462,152 | `55845e39e8510c64e1d7421b87c332d893a17b1ba3d9694f4c2e7a92a8d2b0fe` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 142 | `Manoj Vaibhav Gems _N_ Jewellers Limited_IPO Note.pdf`<br>Manoj Vaibhav Gems _N_ Jewellers Limited | 429,735 | `7430bc40a8104d4e8ebf7ec9cca3153e68506bfb9aae649fee9546dcb4cf6808` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 143 | `Medi Assist Healthcare Services  Limited_IPO Note.pdf`<br>Medi Assist Healthcare Services  Limited | 414,777 | `30d14c8b941667f4568ca733049971cdaefb6f18b7f6ef14acce863df41d82a7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 144 | `Meesho Ltd_IPO Note.pdf`<br>Meesho Ltd | 641,721 | `5d94423c6f347ce129cdba52b0f92833c06cc960b1ae82419d6b64f003cecea9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 145 | `Midwest Ltd_IPO Note.pdf`<br>Midwest Ltd | 579,672 | `4dc871ba322501c3ed7d3428d90354deb95aaa9c37b232a92853894c2b6496fb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 146 | `Muthoot Microfin Limited_IPO Note.pdf`<br>Muthoot Microfin Limited | 408,860 | `affe569f316d3134918ae26b00e614511aa35f0d22f03ba9b29160ac0f40df09` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 147 | `NTPC Green Energy Ltd_IPO Note.pdf`<br>NTPC Green Energy Ltd | 573,442 | `7c4f61431f6639806fdccdc0e3e86f15cabadc81445f726ec350a02d358c8944` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 148 | `National Securities Depository Limited_IPO Note.pdf`<br>National Securities Depository Limited | 520,190 | `28454a8cfc5e641c891d78718226d48049658fe50662dd6c94d1f45c49b1b0fe` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 149 | `Nephrocare Health Services Ltd_IPO Note.pdf`<br>Nephrocare Health Services Ltd | 683,105 | `e2006143c5d50eb73f463199396c045d0bbe9c651643ad729882d61abad2278b` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 150 | `Netweb Technologies India Limited_IPO NOTE_17-07-2023.pdf`<br>Netweb Technologies India Limited | 441,157 | `2c9dd5ecf50bbade4c678868dc853726b199dbd8c7ee2f21f7b2c25b43a3e2c3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 151 | `Nexus Select Trust _REIT__IPO Note.pdf`<br>Nexus Select Trust _REIT_ | 1,324,622 | `313c434fd47cdf9fc6c8777eaa9c24a21276e63c0119f4922463329080fd0d89` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 152 | `Niva Bupa Health Insurance Company Limited_IPO Note.PDF`<br>Niva Bupa Health Insurance Company Limited | 525,853 | `35e0db5d0e5bd416b99c02f3addfba3262d88e5d0944aa0ef5313357e4cfc5a7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 153 | `Northern Arc Capital Ltd_IPO Note.pdf`<br>Northern Arc Capital Ltd | 464,545 | `e49ef0f0100421aa4b6fe7ab70bd1be6dec90f448f8ebf4aa66c872ac33cd97e` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 154 | `Ola Electric Mobility Limited_IPO Note.pdf`<br>Ola Electric Mobility Limited | 643,283 | `d5a390595c07fdd18a5d240a18c8d0981a37d23f0b855bc1bbf25bea1eefc98d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 155 | `Om Power Transmission Ltd_IPO Note.pdf`<br>Om Power Transmission Ltd | 428,524 | `bf3c96070b1732eb3570029873e73aee3cfd98d16a65d66b6046df99c7019892` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 156 | `Omnitech Engineering Ltd_IPO Note.pdf`<br>Omnitech Engineering Ltd | 759,953 | `3d212fc9a3e169998d5eb4c0761853da2b21aa476a8e9c53c8484d38a654c2c2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 157 | `OnEMI Technology Solutions Ltd._IPO Note.pdf`<br>OnEMI Technology Solutions Ltd. | 557,183 | `e444a00155b1ef4436f1ed95b7fc0d150bbfd480aedeb689eac775ef4cc880e9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 158 | `One MobiKwik Systems Ltd_IPO Note.pdf`<br>One MobiKwik Systems Ltd | 651,034 | `68fb5b1cf470607d27163c246682f8afc0855a35acd096bc7c90c4680aecb4ec` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 159 | `Orient Technologies Ltd_IPO Note.PDF`<br>Orient Technologies Ltd | 465,925 | `d5777597bc51e41f80edc6050b3cf662433f08fb2b6dffc7821772b88f1525d4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 160 | `Orkla India Ltd_IPO Note.pdf`<br>Orkla India Ltd | 744,840 | `8682611cf1638f5586d6a44860b721553d3cbb12e66d7c4682046a85625095f2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 161 | `Oswal Pumps Ltd_IPO Note.pdf`<br>Oswal Pumps Ltd | 671,339 | `afd889de76bf54429b97d6bdf334f171f6fe3fe602d8aea0c5969234a0694077` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 162 | `P N Gadgil Jewellers Ltd_IPO Note.pdf`<br>P N Gadgil Jewellers Ltd | 504,214 | `be53d6ea42763393c6528f209ff8f9902152e1a44192a2360ed676159084ba01` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 163 | `PKH Ventures Limited_IPO NOTE_30-06-2023.pdf`<br>PKH Ventures Limited | 523,297 | `72f385c363cb6ed4ba0af15e6a92fc573b7a125bd446db430614a2169d1b1405` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 164 | `PNGS Reva Diamond Jewellery_IPO Note.pdf`<br>PNGS Reva Diamond Jewellery | 525,253 | `6b207df4c27822ca668d2275636494c831b436fd7b46390d7960cfe8e1190d46` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 165 | `Pace Digitek_IPO Note.pdf`<br>Pace Digitek | 653,882 | `f8c4ce163024a221624a926f2160fc3c3bf08f2d59994247b8c6910c4c988775` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 166 | `Park Medi World Ltd_IPO Note.pdf`<br>Park Medi World Ltd | 688,962 | `d6a5da4f0f293d9527a6e66c8d6234c112afc3d3e9851fd437a26a51e08c81fa` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 167 | `Patel Retail Ltd_IPO Note.pdf`<br>Patel Retail Ltd | 417,476 | `c86729fce92f58cd9bbc472dad74fb4f6f4fdc6d11f107de5c4aa53e90786c82` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 168 | `PhysicsWallah Ltd_IPO Note.pdf`<br>PhysicsWallah Ltd | 963,128 | `5cf11e616186bb7e08acc2ae913ef2366c12f4964079b5d9fb2aaadc1695a726` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 169 | `Pine Labs Ltd_IPO Note.pdf`<br>Pine Labs Ltd | 590,298 | `1aced55a3cc28bdc390d00c4487efa8ccd89168086009fe986b2ab01b9a7d8f2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 170 | `Popular Vehicles and Services Limited_IPO Note.pdf`<br>Popular Vehicles and Services Limited | 461,727 | `e9f07753edd0d9e2838feb8eed40fb199fb8c71512a5c5ef71c51258e214faf0` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 171 | `Powerica Ltd_IPO Note.pdf`<br>Powerica Ltd | 558,910 | `bed44a8d0af514c752818d26b18fb25b308ec6190da16eab5d6ae4fe263a48ef` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 172 | `Premier Energies Limited_IPO Note.pdf`<br>Premier Energies Limited | 475,059 | `efdfe1497f15487bc7c86aea42f20fccdc002e0aa52812d9d9db88726a166e0c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 173 | `Privacy-Policy.pdf`<br>Privacy-Policy | 159,262 | `8fe5d0f395e4dda238f541c0a244b97e694b166a9f4337be66eb562fcf0b0849` | UNKNOWN | UNKNOWN | UNKNOWN | IPO_RESOLUTION_MISSING |
| 174 | `Prostarm Info Systems Ltd_IPO Note.pdf`<br>Prostarm Info Systems Ltd | 387,616 | `ebc9827844ca4164f56f669e9a9c93592a334066c13dca6a4594634b8b7db6f2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 175 | `Protean eGov Technologies Limited_IPO Note.pdf`<br>Protean eGov Technologies Limited | 474,573 | `ee43cd96f0759b6311871ec453433488e4c924146d1aa2a539a718e70c3b4559` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 176 | `Pyramid Technoplast Limited_IPO Note.pdf`<br>Pyramid Technoplast Limited | 471,264 | `4d4e8b3c430747a986cf9813922ca6107852f39baac5ae659a0a3a81af996008` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 177 | `Quadrant Future Tek  Limited_IPO Note.pdf`<br>Quadrant Future Tek  Limited | 494,267 | `030534c0d9d45f08582fcb77ca49e3cc43bdec693f19069da53a35f881002c78` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 178 | `R K Swamy Limited_IPO Note.pdf`<br>R K Swamy Limited | 530,249 | `db03c209edd8f13e8d957df571bd3f92e8a5757920257dfa8d0fda32b3527e36` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 179 | `RR Kabel Limited_IPO Note.pdf`<br>RR Kabel Limited | 440,511 | `1034d4c565316ac0237f72b769396fa3ceb26e9a7574037869713716c9f68ce7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 180 | `Rajputana Stainless Ltd_IPO Note.pdf`<br>Rajputana Stainless Ltd | 604,141 | `10f58fab84ee4de272c78ee838657f7b9602401ead8a2cf9c253bc4fa09f9bb7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 181 | `Rishabh Instruments Limited_IPO Note.pdf`<br>Rishabh Instruments Limited | 445,657 | `7d04db8d61bbf779c3e8782eabc0601d929346a1652e8d137adc1e66d4cec4ea` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 182 | `Rubicon Research Ltd_IPO Note.pdf`<br>Rubicon Research Ltd | 559,414 | `cf454275e548102359445ad7e24e713481504f0ab2d0f8892d3d43ff2164b127` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 183 | `SBFC Finance Limited_IPO NOTE_02-08-2023.pdf`<br>SBFC Finance Limited | 506,968 | `80ff084d93293d0d460940fa55872f3203f025792d430e3793e8dd205749f089` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 184 | `SBI Securities_Rashi Peripherals Limited_IPO Note.pdf`<br>SBI Securities_Rashi Peripherals Limited | 490,967 | `eb95331e63cb75af4d6d14dfe7608f7ab21b0b0eaf12ec8f5a8eba84be231385` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 185 | `Saatvik Green Energy Ltd_IPO Note.pdf`<br>Saatvik Green Energy Ltd | 1,250,620 | `d8ba50fa3a1b4f4cdd82c655310a2c189dd258b92197fa4995d8fae8bafe1ef2` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 186 | `Sagility India Ltd_IPO Note.pdf`<br>Sagility India Ltd | 526,152 | `1efdea27204e54cb2d0ee416051a9e572374db3d01868193614923f606d79252` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 187 | `Sai Life Sciences Ltd_IPO Note.pdf`<br>Sai Life Sciences Ltd | 559,327 | `67ccdba64ac0a71d849c11b91af4aabbce1753a56cb22a270efb8b720c4a188e` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 188 | `Sai Parenteral_s Ltd_IPO Note_1.pdf`<br>Sai Parenteral_s Ltd | 799,773 | `0c784206b60843110c3114a20bae55f685c7d540ccbd4aba50d73e8416bfd192` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 189 | `Sai Silk _Kalamandir_ Limited_IPO Note.pdf`<br>Sai Silk _Kalamandir_ Limited | 469,456 | `e5128572c6c83343385df7137bd2a6a6c679e214a88f48a54abe45e2657cf059` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 190 | `Sambhv Steel Tubes Ltd_IPO Note.pdf`<br>Sambhv Steel Tubes Ltd | 663,431 | `14db61164ec1fea5cac2a601963f99c766e696f9b99cb2c507c9b9ae4bbb7923` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 191 | `Sanathan Textiles Ltd_IPO Note.pdf`<br>Sanathan Textiles Ltd | 481,089 | `c415a84515efb63bcdcd4ba39d2ac9f2954c6424478d2c4c4566cf7e5eb46f9d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 192 | `Sanstar Limited_IPO Note.PDF`<br>Sanstar Limited | 457,294 | `6720b75551d64f8e8740bd4f95b90dbc9ab91fa339b03abc9dca5e2b27df98f6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 193 | `Schloss Bangalore Ltd_IPO Note.pdf`<br>Schloss Bangalore Ltd | 571,731 | `4e2b869f3374daa82c92979bff473302225ba0d1cf0d1a3a99df9f6f168bc368` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 194 | `Scoda Tubes Ltd_IPO Note.pdf`<br>Scoda Tubes Ltd | 417,092 | `aedd43b5ba2587a51e3ecf2da58cff029a1e06e26bb50df7857c9c91dd4e42df` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 195 | `Sedemac Mechatronics_IPO Note.pdf`<br>Sedemac Mechatronics | 560,802 | `e08dd7ba663b731e278b886a817f1e49e6a9718f6987a500d97e618dda9979c4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 196 | `Senco Gold Ltd_IPO Note.pdf`<br>Senco Gold Ltd | 583,504 | `32c045b995c45237e8c8f3d38002409bd0068c0adddf475b7d19939e0274aa8d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 197 | `Senores Pharmaceuticals Ltd_IPO Note.pdf`<br>Senores Pharmaceuticals Ltd | 739,525 | `bfba178d8838472ce13df3c155fe956130ea8db1561982232628497acab09791` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 198 | `Seshaasai Technologies Ltd_IPO Note.pdf`<br>Seshaasai Technologies Ltd | 569,357 | `d3eeca89f5af47471abfb4567ec2a7c5ba82b1194f9bb2524ce3e962fd053dfb` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 199 | `Shadowfax Technologies Ltd_IPO Note.pdf`<br>Shadowfax Technologies Ltd | 1,203,444 | `88fb58c346a339b329b8778fc38ddc2e6271a7758cbacf392dff5a1c7555d171` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 200 | `Shanti Gold International Ltd_IPO Note.pdf`<br>Shanti Gold International Ltd | 533,546 | `3e0b7fa8d80442f3ea464083ab6f7175a1d7048a293c634bd260406cba04a97d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 201 | `Shreeji Shipping Global Ltd_IPO Note.pdf`<br>Shreeji Shipping Global Ltd | 593,996 | `d8940dd7037d283e86562f2eeeb18fcb8ead329c4e4ff41e9011ab9346522708` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 202 | `Shringar House of Mangalsutra Ltd_IPO Note.pdf`<br>Shringar House of Mangalsutra Ltd | 1,083,940 | `b78a8b420eacb083022f6aa25cbe55636e181714b9d6e8e24fd6c051f26568b6` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 203 | `Smartworks Coworking Spaces Limited_IPO Note.pdf`<br>Smartworks Coworking Spaces Limited | 977,639 | `adba934914ca356324b976ccc769673ce57ea5a449a6eba78a1782f6939dc7a1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 204 | `Solarworld Energy Solutions Ltd_IPO Note.pdf`<br>Solarworld Energy Solutions Ltd | 512,081 | `f976c2df0caf0f45db26d249df08eccea9420c35a2a9d41677792401bd25e476` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 205 | `Sri Lotus Developers and Realty Ltd_IPO Note.pdf`<br>Sri Lotus Developers and Realty Ltd | 650,894 | `1f81a66281b61d8a508df44d0238d27fadda46e852105aa3c0df83719ea2e54b` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 206 | `Standard Glass Lining Technology Ltd_IPO Note.pdf`<br>Standard Glass Lining Technology Ltd | 513,531 | `3d5620c54b43dcd87e1a03399775cf1fd433338ebf2ce26af5680a738c824fa1` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 207 | `Stanley Lifestyles Limited_IPO Note.pdf`<br>Stanley Lifestyles Limited | 487,347 | `b045e7b6ee5a08029083c33e874bd348e9be309baa21ec2eefc366b167ce04da` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 208 | `Studds Accessories Ltd_IPO Note.pdf`<br>Studds Accessories Ltd | 660,076 | `1a765002f751a66845593e6e03601aa9cdc66555a3e483d276df0cc55a58f69d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 209 | `Sudeep Pharma Ltd_IPO Note.pdf`<br>Sudeep Pharma Ltd | 672,064 | `4187650aef57b3eee6b1528bec53b3503c157647b9c07012b1c43d80f798dd44` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 210 | `Suraksha Diagnostic Ltd_IPO Note.pdf`<br>Suraksha Diagnostic Ltd | 422,831 | `78fbfc555fd460469800a3b3b3c20c1ffe47a3010f3080ab3d043413b4310c3c` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 211 | `Swiggy Ltd_IPO Note.pdf`<br>Swiggy Ltd | 499,629 | `0a8233015bf63dfdb9702ea16d30aaa8252401310ae8ecf01aa341530fe36b6e` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 212 | `TBO Tek Limited_IPO Note.pdf`<br>TBO Tek Limited | 522,584 | `a6269bb5d079fa2d4252c829b07f8565cfeedd2e271bfb613795f3a460c129bf` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 213 | `TVS Supply Chain Solutions Limited_IPO Note.pdf`<br>TVS Supply Chain Solutions Limited | 473,599 | `2ad1de457e2c94548c57209d5ab340a07181d8bcff0e333cebf48e6d657b01b4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 214 | `Tata Capital Ltd_IPO Note.pdf`<br>Tata Capital Ltd | 674,951 | `f9eb974d0c42eafc32fcf11c136c7b22ad06a6c563743cbb93747191d3f09001` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 215 | `Tata Technologies Limited_IPO Note.pdf`<br>Tata Technologies Limited | 867,521 | `d191fe221158a589593a74e76e20eccb5d7c8f22dc77bf5fb37aa25d4d96015b` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 216 | `Tenneco Clean Air India Ltd_IPO Note.pdf`<br>Tenneco Clean Air India Ltd | 639,807 | `328c35039ed9959c49088b8ff80aea984eb8888b032dde835a0f6e3c0b8cd846` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 217 | `Transrail Lighting Limited_IPO Note.pdf`<br>Transrail Lighting Limited | 569,289 | `50793cc557ee1f42333d43a0b6590fd969872392460540c3f0d59143b232b2a3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 218 | `Travel Food Services Ltd_IPO Note.pdf`<br>Travel Food Services Ltd | 567,031 | `3131585fd920f4bfbd778efaad2ef07d5a72c45dc68d8ab14778f405c147daa4` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 219 | `TruAlt Bioenergy Ltd_IPO Note.pdf`<br>TruAlt Bioenergy Ltd | 591,393 | `8e8fb005238899db95797c364c1bb89d03f44d8744e27e32b86fd0fcba69bc43` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 220 | `Turtlemint Fintech Solutions_IPO Note.pdf`<br>Turtlemint Fintech Solutions | 556,027 | `fc8ec9bd39864899a9223245cf4ea6b29b8c39822f611939520f55042760c9ec` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 221 | `Unicommerce eSolutions Ltd_IPO Note.pdf`<br>Unicommerce eSolutions Ltd | 391,103 | `2642691ba1b21842819403ec7753c0fe8caf1f805e36effa9fbd2190847548b5` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 222 | `Unimech Aerospace and Manufacturing Ltd_IPO Note.pdf`<br>Unimech Aerospace and Manufacturing Ltd | 422,012 | `a79b58c313a954e3e0d83416f3b6dc05541069a47fc8b22d1539d904b328b3bd` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 223 | `Updater Services Limited_IPO Note.pdf`<br>Updater Services Limited | 518,019 | `1ba38e0113ea6889c839249123ae495e2ca336459a069432d007131e8aab20f3` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 224 | `Urban Company Limited_IPO Note.pdf`<br>Urban Company Limited | 538,690 | `f09bc0efd822956afc7bebd335104a6adc9a034b0ecafe808ca60f0a745f9349` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 225 | `Utkarsh Small Finance Bank Limited_IPO NOTE.pdf`<br>Utkarsh Small Finance Bank Limited | 498,257 | `111ffbde57cebeb2019232b10fa806e863e7fb1a57c5db71a27b08d62f9afc40` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 226 | `Ventive Hospitality Ltd_IPO Note.pdf`<br>Ventive Hospitality Ltd | 529,051 | `57d7c9e1e06cd42191b1febcf74df90817b4b5647062be2c3c630d4332321ad5` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 227 | `Vidya Wires Ltd_IPO Note.pdf`<br>Vidya Wires Ltd | 610,492 | `f3a39164d1d96ef1a3f5eb8df5944666d99203e609fc02a6cb5666a5283ae1ff` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 228 | `Vikram Solar Ltd_IPO Note.pdf`<br>Vikram Solar Ltd | 691,462 | `4c1ed4132ebfb9d93e03f177bbfdf2a6e0b02cff2b8595d5000c9e90519244a9` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 229 | `Vikran Engineering Ltd_IPO Note.pdf`<br>Vikran Engineering Ltd | 559,772 | `bd0d9cc5ff4cd5c276d0e39fedfb9c5096114831a2f43c3dd1c113ea93e6897d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 230 | `Vishal Mega Mart Ltd_IPO Note.pdf`<br>Vishal Mega Mart Ltd | 481,413 | `dd607c47d0080eeb4fe2fb6ae6afd11ab62fb2c90edd3ec67ebb353ffe4fcd85` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 231 | `Vodafone Idea Limited_FPO Note.pdf`<br>Vodafone Idea Limited | 478,183 | `8a19a9ff637404605ea1e4d0b65133121ad812658992cdb55e6b02029d4097bf` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 232 | `Waaree Energies Ltd_IPO Note.pdf`<br>Waaree Energies Ltd | 585,924 | `05a75897214626674f848ab8443f5b8817bf000dcc8a6a64800c08e61f0485c8` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 233 | `Wakefit Innovations Ltd_IPO Note.pdf`<br>Wakefit Innovations Ltd | 583,864 | `2092ca6d3a68be83ce7a76ef73354c3ec78bfff36baaee559d3475ee2b39564d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 234 | `Waterways Leisure Toursim Ltd._IPO Note.pdf`<br>Waterways Leisure Toursim Ltd. | 437,621 | `a9ba6ab68082c7901d1cb110eb16c641e68f0c7399d7a49eab1ebb6b608d2a1a` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 235 | `WeWork India Management Ltd_IPO Note.pdf`<br>WeWork India Management Ltd | 652,584 | `88c534ec795b3408190bf0446c6ef95adee3757c55db0a8d72b1bbb39cad8f75` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 236 | `Western Carriers _India_ Ltd_IPO Note.pdf`<br>Western Carriers _India_ Ltd | 590,391 | `0536ddf6246a5ca1eb50edf973da63209e00906263add3136d696fe0d85ee92d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 237 | `Yatra Online Ltd_IPO Note.pdf`<br>Yatra Online Ltd | 578,470 | `111097ecb690807a57d2212c84a9b821f8a63f1bcf62b1953268ceffb96aa43d` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 238 | `Zaggle Prepaid Ocean Services Limited_IPO Note.pdf`<br>Zaggle Prepaid Ocean Services Limited | 478,284 | `d1c80419557570c07c6a29b0a10f2a6ffd88e77f26ffacc3d7c003f2eb8fe0e7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 239 | `Zinka Logistics Solutions Ltd_IPO Note.pdf`<br>Zinka Logistics Solutions Ltd | 502,034 | `33339497772d2462c4195841bd3e42620f911776e04ef96745f03f7bd23959b7` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 240 | `iValue Infosolutions Ltd_IPO Note.pdf`<br>iValue Infosolutions Ltd | 539,321 | `1aba4807279150ccd0d21983fc6b91174c9fda4971a8959392698f3d28a4affc` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |
| 241 | `ideaForge Technology Limited_IPO NOTE_26-06-2023.pdf`<br>ideaForge Technology Limited | 484,686 | `e9d33281959ceb18bb291c2594ae0918f7e4c8c41101b8aea013d8b03c741583` | UNKNOWN | UNKNOWN | UNKNOWN | READY_FOR_INGEST |

## Aggregate dry-run result

`TOTAL=241 LEDGERED=0 R2_VERIFIED=0 SHA_MATCH=0 EXTRACTED=0 UNRESOLVED=0 MISSING=0 MISMATCH=0`

Zeros other than TOTAL mean **not checked in local-only mode**, not proven absence.
