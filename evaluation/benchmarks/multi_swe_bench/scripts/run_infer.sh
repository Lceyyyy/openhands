#!/bin/bash
set -eo pipefail

source "evaluation/utils/version_control.sh"

MODEL_CONFIG=$1
COMMIT_HASH=$2
AGENT=$3
EVAL_LIMIT=$4
MAX_ITER=$5
NUM_WORKERS=$6
DATASET=$7
# SPLIT=$8
LANGUAGE=$8
# N_RUNS=$10

if [ -z "$NUM_WORKERS" ]; then
  NUM_WORKERS=1
  echo "Number of workers not specified, use default $NUM_WORKERS"
fi
checkout_eval_branch

if [ -z "$AGENT" ]; then
  echo "Agent not specified, use default CodeActAgent"
  AGENT="CodeActAgent"
fi

if [ -z "$MAX_ITER" ]; then
  echo "MAX_ITER not specified, use default 100"
  MAX_ITER=100
fi

if [ -z "$USE_INSTANCE_IMAGE" ]; then
  echo "USE_INSTANCE_IMAGE not specified, use default true"
  USE_INSTANCE_IMAGE=true
fi

if [ -z "$RUN_WITH_BROWSING" ]; then
  echo "RUN_WITH_BROWSING not specified, use default false"
  RUN_WITH_BROWSING=false
fi


if [ -z "$DATASET" ]; then
  echo "DATASET not specified, use default princeton-nlp/SWE-bench_Lite"
  DATASET="princeton-nlp/SWE-bench_Lite"
fi

if [ -z "$LANGUAGE" ]; then
  echo "LANUGUAGE not specified, use default python"
  LANGUAGE="python"
fi

if [ -z "$SPLIT" ]; then
  echo "LANUGUAGE not specified, use default python"
  SPLIT="train"
fi

##TODO:适配多语言的版本
# if [ -z "$SPLIT" ]; then
#   if [ "$LANGUAGE" = "python" ]; then
#   echo "SPLIT is test as LANUGUAGE is python"
#     SPLIT="test"
#   elif [ "$LANGUAGE" = "java" ]; then
#   echo "SPLIT is java_verified as LANUGUAGE is java"
#     SPLIT="java_verified"
#   fi
# fi

if [ -z "$EVAL_DOCKER_IMAGE_PREFIX" ]; then
  if [ "$LANGUAGE" = "python" ]; then
  echo "EVAL_DOCKER_IMAGE_PREFIX is docker.io/xingyaoww/ as default as LANUGUAGE is python"
    EVAL_DOCKER_IMAGE_PREFIX="docker.io/xingyaoww/"
  elif [ "$LANGUAGE" = "java" ]; then
  echo "EVAL_DOCKER_IMAGE_PREFIX is java_verified as LANUGUAGE is java"
    EVAL_DOCKER_IMAGE_PREFIX=""
  fi
fi

export EVAL_DOCKER_IMAGE_PREFIX=$EVAL_DOCKER_IMAGE_PREFIX
echo "EVAL_DOCKER_IMAGE_PREFIX: $EVAL_DOCKER_IMAGE_PREFIX"
export USE_INSTANCE_IMAGE=$USE_INSTANCE_IMAGE
echo "USE_INSTANCE_IMAGE: $USE_INSTANCE_IMAGE"
export RUN_WITH_BROWSING=$RUN_WITH_BROWSING
echo "RUN_WITH_BROWSING: $RUN_WITH_BROWSING"
export LANGUAGE=$LANGUAGE
echo "LANGUAGE: $LANGUAGE"

# 添加swe-bench MCP过滤配置
export SWE_BENCH_MCP_FILTER=true
export SWE_BENCH_EVAL_MODE=true
echo "SWE_BENCH_MCP_FILTER: $SWE_BENCH_MCP_FILTER"
echo "SWE_BENCH_EVAL_MODE: $SWE_BENCH_EVAL_MODE"

get_openhands_version

echo "AGENT: $AGENT"
echo "OPENHANDS_VERSION: $OPENHANDS_VERSION"
echo "MODEL_CONFIG: $MODEL_CONFIG"
echo "DATASET: $DATASET"
echo "SPLIT: $SPLIT"

# Default to NOT use Hint
if [ -z "$USE_HINT_TEXT" ]; then
  export USE_HINT_TEXT=false
fi
echo "USE_HINT_TEXT: $USE_HINT_TEXT"
EVAL_NOTE="$OPENHANDS_VERSION"
# if not using Hint, add -no-hint to the eval note
if [ "$USE_HINT_TEXT" = false ]; then
  EVAL_NOTE="$EVAL_NOTE-no-hint"
fi

if [ "$RUN_WITH_BROWSING" = true ]; then
  EVAL_NOTE="$EVAL_NOTE-with-browsing"
fi

if [ -n "$EXP_NAME" ]; then
  EVAL_NOTE="$EVAL_NOTE-$EXP_NAME"
fi

function run_eval() {
  local eval_note=$1
  COMMAND="poetry run python evaluation/benchmarks/multi_swe_bench/run_infer.py \
    --agent-cls $AGENT \
    --llm-config $MODEL_CONFIG \
    --max-iterations $MAX_ITER \
    --eval-num-workers $NUM_WORKERS \
    --eval-note $eval_note \
    --dataset $DATASET \
    --split $SPLIT"

  if [ -n "$EVAL_LIMIT" ]; then
    echo "EVAL_LIMIT: $EVAL_LIMIT"
    COMMAND="$COMMAND --eval-n-limit $EVAL_LIMIT"
  fi

  # Run the command
  eval $COMMAND
}

unset SANDBOX_ENV_GITHUB_TOKEN # prevent the agent from using the github token to push
if [ -z "$N_RUNS" ]; then
  N_RUNS=1
  echo "N_RUNS not specified, use default $N_RUNS"
fi

# Skip runs if the run number is in the SKIP_RUNS list
# read from env variable SKIP_RUNS as a comma separated list of run numbers
SKIP_RUNS=(${SKIP_RUNS//,/ })
for i in $(seq 1 $N_RUNS); do
  if [[ " ${SKIP_RUNS[@]} " =~ " $i " ]]; then
    echo "Skipping run $i"
    continue
  fi
  current_eval_note="$EVAL_NOTE-run_$i"
  echo "EVAL_NOTE: $current_eval_note"
  run_eval $current_eval_note
done

checkout_original_branch
