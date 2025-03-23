import concurrent.futures
import datetime
import hashlib
import json
import os
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



class Artifact:
    def __init__(self, data: Any, name: str):
        self.data = data
        self.name = name
        self.timestamp = datetime.datetime.now()
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        return hashlib.sha256(str(self.data).encode()).hexdigest()

    def __repr__(self):
        return f"Artifact(name={self.name}, hash={self.hash})"

class Step:
    def __init__(self, func: Callable, inputs: List[str] = [], outputs: List[str] = [], config=None):
        self.func = func
        self.inputs = inputs
        self.outputs = outputs
        self.name = func.__name__
        self.config=config or{}

    def execute(self, artifacts: Dict[str, Artifact]) -> Dict[str, Artifact]:
        input_values = [artifacts[name].data for name in self.inputs]
        output_values = self.func(*input_values)

        if not isinstance(output_values, tuple):
             output_values = (output_values,)

        if len(output_values) != len(self.outputs):
            raise ValueError("Number of outputs does not match expected number")


        end_time = time.time()
        execution_time = end_time - start_time
        logging.info(f"Step {self.name} executed in {execution_time:.2f} seconds.")

        return {name: Artifact(data, name) for name, data in zip(self.outputs, output_values)}

class Pipeline:
    def __init__(self, name: str, steps: List[Step]):
        self.name = name
        self.steps = steps
        self.artifact_store = {}

    def run(self, stack: "Stack", parallel: bool = True):
        if parallel:
            self._run_parallel(stack)
        else:
            self._run_sequential(stack)

    def _run_parallel(self, stack: "Stack"):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}
            for step in self.steps:
                dependencies_met = True
                for input_name in step.inputs:
                    if input_name not in self.artifact_store:
                        dependencies_met = False
                        break

                if dependencies_met:
                    futures[step] = executor.submit(step.execute, self.artifact_store)

            for step, future in concurrent.futures.as_completed(futures.values()):
                try:
                    results = future.result()
                    self.artifact_store.update(results)
                    stack.log_artifacts(results)
                except Exception as e:
                    logging.error(f"Error in step execution: {e}", exc_info=True)

    def _run_sequential(self, stack: "Stack"):
        for step in self.steps:
            dependencies_met = True
            for input_name in step.inputs:
                if input_name not in self.artifact_store:
                    dependencies_met = False
                    break

            if dependencies_met:
                try:
                    results = step.execute(self.artifact_store)
                    self.artifact_store.update(results)
                    stack.log_artifacts(results)
                except Exception as e:
                    logging.error(f"Error in step execution: {e}", exc_info=True)
                    break # Stop if error in sequential mode.

    def save_pipeline(self, filename: str = "artifacts/pipeline_state.json"):
        with open(filename, "w") as file:
            json.dump(self.execution_metadata, file, indent=4)
        logging.info(f"Pipeline state saved to {filename}")

    def visualize_pipeline(self, output_file: str = "artifacts/pipeline_graph"):
        G = nx.DiGraph()

        # Add nodes and edges
        for step in self.steps:
            G.add_node(step.name)
            for input_name in step.inputs:
                G.add_edge(input_name, step.name)
            for output_name in step.outputs:
                G.add_edge(step.name, output_name)

        # Draw the graph
        plt.figure(figsize=(10, 6))
        pos = nx.spring_layout(G, seed=42)  # Layout algorithm for positioning
        nx.draw(
            G,
            pos,
            with_labels=True,
            node_color="lightblue",
            edge_color="gray",
            node_size=2000,
            font_size=10,
            font_weight="bold",
        )

        # Save and show
        plt.savefig(f"{output_file}.png")
        plt.show()
        logging.info(f"Pipeline visualization saved as {output_file}.png")

class Stack:
    def __init__(self, name: str, artifact_root: str):
        self.name = name
        self.artifact_root = artifact_root
        os.makedirs(artifact_root, exist_ok=True)

    def log_artifacts(self, artifacts: Dict[str, Artifact]):
        for name, artifact in artifacts.items():
            artifact_path = os.path.join(self.artifact_root, f"{name}_{artifact.hash}.json")
            with open(artifact_path, "w") as f:
                json.dump({"data": str(artifact.data), "timestamp": str(artifact.timestamp)}, f)

    def deploy_model(self, model: Artifact, deployment_path: str):
        os.makedirs(deployment_path, exist_ok=True)
        model_path = os.path.join(deployment_path, f"{model.name}_{model.hash}.json")
        with open(model_path, "w") as f:
            json.dump({"data": str(model.data), "timestamp": str(model.timestamp)}, f)
        print(f"Model deployed to {model_path}")

    def monitor_model(self, model: Artifact, data: Any) -> Any:
        # Simple monitoring example: just run the model
        return model.data(data)

class CloudStack(Stack):
    def log_artifacts(self, artifacts: Dict[str, Artifact]):
        # Example using boto3 (AWS S3)
        import boto3
        s3 = boto3.client('s3')
        bucket_name = "your-s3-bucket"
        for name, artifact in artifacts.items():
            object_key = f"{self.artifact_root}/{name}_{artifact.hash}.json"
            s3.put_object(Bucket=bucket_name, Key=object_key, Body=json.dumps({"data": str(artifact.data), "metadata": artifact.metadata}).encode())

    def deploy_model(self, model: Artifact, deployment_path: str):
        #Example of Lambda deployment
        print(f"Model deployed to Lambda using path: {deployment_path}")

    def monitor_model(self, model: Artifact, data: Any) -> Any:
        #Example of CloudWatch monitoring.
        print(f"Monitoring prediction using cloudwatch for data: {data}")
        return super().monitor_model(model, data)

# Example ML functions
class LoadData:
    def load_data():
        return [1, 2, 3, 4, 5]

class TrainModel:
    def train_model(data):
        def simple_model(x):
            return x * 2
        return simple_model

class EvaluateModel:
    def evaluate_model(model, data):
        results = [model(x) for x in data]
        return sum(results) / len(results)

# Example Usage

local_stack = Stack("local", "artifacts/local")

load_step = Step(LoadData().load_data, outputs=["data"])
train_step = Step(TrainModel().train_model, inputs=["data"], outputs=["model"], params={"learning_rate": 0.2})
eval_step = Step(EvaluateModel().evaluate_model, inputs=["model", "data"], outputs=["evaluation"])

pipeline = Pipeline("example_pipeline", [load_step, train_step, eval_step])

# Run in parallel
print("Running pipeline in parallel:")
start_time_parallel = time.time()
pipeline.run(local_stack, parallel=True)
end_time_parallel = time.time()
print(f"Parallel execution time: {end_time_parallel - start_time_parallel:.2f} seconds")

# Reset artifact store
pipeline.artifact_store = {}

# Run in sequential
print("\nRunning pipeline sequentially:")
start_time_sequential = time.time()
pipeline.run(local_stack, parallel=False)
end_time_sequential = time.time()
print(f"Sequential execution time: {end_time_sequential - start_time_sequential:.2f} seconds")


local_stack = Stack("local", "artifacts/local")

load_step = Step(load_data, outputs=["data"])
train_step = Step(train_model, inputs=["data"], outputs=["model"])
eval_step = Step(evaluate_model, inputs=["model", "data"], outputs=["evaluation"])

pipeline = Pipeline("example_pipeline", [load_step, train_step, eval_step])
pipeline.run(local_stack)

# Deployment and Monitoring
trained_model = pipeline.artifact_store["model"]
local_stack.deploy_model(trained_model, "deployments/local")

test_data = 6
prediction = local_stack.monitor_model(trained_model, test_data)
print(f"Prediction for {test_data}: {prediction}")