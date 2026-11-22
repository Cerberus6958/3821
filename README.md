# 3821

Github repo for COMP3821 Project  

To run, you can run  ```python3 taxi_sim.py``` and pass in a number of optional arguments, as per the table below.

| Optional Arg | Default Value | What it does |
| -------- | -------- | -------- |
| --cars   | 10        | The total number of cars available to pickup  |
| --homes | 30 | The total number of homes to pick up from |
| --workplaces | 6 | The total number of workplaces to deliver to |
| --trips | 200 | The total number of trip requests in a day|
| --size | 20.0 | Size of the town |
| --speed | 40.0 | Speed of the cars |
| --iters | 20000 | Number of different attempts it makes to improve optimisation |
| --seed | 1 | Seed for randomisation |
| --trips-file | none | Load a predefined set of trips if you want |
| --csv | none | Produce a file of the results |


## Robotaxi lab and report experiments

- `robotaxi-lab/`: interactive simulator with three problems (base, simplified, online). See `robotaxi-lab/README.md`; run with `cd robotaxi-lab && python run.py`.
- `experiments/`: the scripts behind every table and figure in the final report. See `experiments/README.md`.
