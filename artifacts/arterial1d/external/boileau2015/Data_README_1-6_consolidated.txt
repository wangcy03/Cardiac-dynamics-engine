A benchmark study of numerical schemes for one-dimensional arterial blood flow modelling
"Etienne Boileau, Perumal Nithiarasu, Pablo J. Blanco, Lucas O. Muller, Fredrik Eikeland Fossan, Leif Rune Hellevik,"
"Wouter P. Donders, Wouter Huberts, Marie Willemet, Jordi Alastruey"
Int. J. Numer. Meth. Biomed. Engng. 2015



# Benchmark1_SinglePulseModel.zip -----------------------------------------
Refer to Table I-II and Equation (14) of the above-cited article.
All files are tab or space separated.

Files in this data supplement:

In NumData:

"Filename: X_Y.txt, with X={DCG,LCG,FEM,FVM,McC,STM}, Y={inviscid,viscous}"
col 1: distance [m]
"col 2 to 9: pressure [kPa] for t={0.1,0.3,0.5,0.7,0.9,1.1,1.3,1.5} [s]"



# Benchmark2_CommonCarotidArtery.zip --------------------------------------
Refer to Table I and III of the above-cited article.
Initial and end time of the last cardiac cycle
tini = 8.8 s
tend = 9.9 s

All files are tab or space separated.

Files in this data supplement:

Filename: inflow.txt (prescribed flow rate at inlet) [ml/s]

In NumData:

"Filename: X.txt, with X={3D,DG,LCG,FEM,FV,McC,STM}"
col 1: time [s]
col 2: pressure [kPa]
col 3: flow rate [ml/s]
col 4: change in radius from diastole [mm]
col 5: pressure gradient between inlet and outlet [kPa]



# Benchmark3_UpperThoracicAorta.zip ---------------------------------------
Refer to Table I and V of the above-cited article.
Initial and end time of the last cardiac cycle
tini = 19.045 s
tend = 20.0 s

All files are tab or space separated.

Files in this data supplement:

Filename: inflow.txt (prescribed flow rate at inlet) [ml/s]

In NumData:

"Filename: X.txt, with X={3D,DCG,LCG,FEM,FVM,McC,STM}"
col 1: time [s]
col 2: pressure [kPa]
col 3: flow rate [ml/s]
col 4: change in radius from diastole [mm]
col 5: pressure gradient between inlet and outlet [kPa]



# Benchmark4_AorticBifurcation.zip ----------------------------------------
Refer to Table I and VII of the above-cited article.
Initial and end time of the last cardiac cycle
tini = 28.6 s
tend = 29.7 s

All files are tab or space separated.

Files in this data supplement:

Filename: inflow.txt (prescribed flow rate at inlet) [ml/s]

In NumData:

"Filename: X_Y.txt, with X={3D,DCG,LCG,FEM,FVM,McC,STM} and Y={AortaMid,Junction,IliacMid}"
col 1: time [s]
col 2: pressure [kPa]
col 3: flow rate [ml/s]
col 4: change in radius from diastole [mm]



# Benchmark5_37ArteryNetwork.zip ------------------------------------------
Refer to Table I and IX of the above-cited article.
All files are tab or space separated.

Files in this data supplement:

Filename: mesh.txt  (tabulated mesh file)
col 1: number of segment
col 2: first node of segment
col 3: last node of segment
col 4: length of segment [m]
col 5: initial radius of segment [m]
col 6: final radius of segment [m]
col 7: wall thickness [m]
col 8: pulse wave velocity PWV at the start of segment [m/s]
col 9: pulse wave velocity PWV at the end of segment [m/s]
col 10: outlet resistance R1 [Pa*s/m3] (if applicable)

Filename: inflow.txt (prescribed flow rate at inlet) [ml/s]

Filename: time_shifts.txt (initial and end time of the last cardiac cycle)

In NumData:

"Filename: X_Y.txt, with X={DCG,LCG,FEM,FVM,McC,STM}, Y={P,Q}"
col 1: time [s]
"col 2 to 9: pressure P [kPa] or flow rate Q [ml/s] for Z={AorticArchII,ThoracicAortaII,LSubclavianI,RIliacFemoralII,LUlnar,RAnteriorTibial,RUlnar,Splenic}"

In ExpData:

"Filename: Z_Y.txt with Z={AorticArchII,ThoracicAortaII,LSubclavianI,RIliacFemoralII,LUlnar,RAnteriorTibial,RUlnar,Splenic}, Y={P,Q}"
col 1: time [s]
col 2: measured pressure P [kPa] or flow rate Q [ml/s]



# Benchmark6_ADAN56.zip ---------------------------------------------------
"Refer to Table I and XI, XII and XII and Figure 10 of the above-cited article."

All files are tab or space separated.

Files in this data supplement:

Filename: network.pdf (graphical representation of ADAN56)

Filename: mesh.txt (tabulated mesh file)
col 1: number of segment
col 2: first node of segment
col 3: last node of segment
col 4: length of segment [cm]
col 5: initial radius of segment [cm]
col 6: final radius of segment [cm]
col 7: resistance R1 [dyne*s/cm5] (if applicable)
col 8: resistance R2 [dyne*s/cm5] (if applicable)
col 9: compliance [cm5/dyne] (if applicable)
col 10: vessel (segment) name

Filename: inflow.txt (prescribed flow rate at inlet)
col 1: time [s]
col 2: flow rate [ml/s]

In NumData:

"Filename: X_Y.txt, with X={DCG,LCG,FEM,FVM,McC,STM}, Y={P,Q}"
col 1: time [s]
"col 2 to 13: pressure P [kPa] or flow rate Q [ml/s] for Z={AorticArchI,ThoAortaIII,AbdomAortaV,RightCCA,RightRenal,RightCommonIliac,RightICA,"
"RightRadial,RightInternalIliac,RightPOstInteross,RightFemoralII,RightAntTibial}"

"Filename: X.txt, with X={DCG,LCG,FEM,FVM,McC,STM}"
col 1: distance along aorta [m]
"col 2 to 7: pressure [kPa] for t={9.1,9.2,9.3,9.5,9.7,1.0} [s]"
col 8: systolic pressure [kPa]
col 9: diastolic pressure [kPa]
col 10: mean pressure [kPa]