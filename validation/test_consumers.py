"""Regression consumers for quotes inside an already-started unquoted target."""
import json
import pandas as pd
import pytest
from vllm.benchmarks.sweep.plot import PlotFilters, SweepPlotArgs, main
from vllm.utils.argparse_utils import FlexibleArgumentParser

REGRESSIONS = ["build=='one", 'build!="one', "version>='one", 'release<"one']

@pytest.mark.parametrize('target', REGRESSIONS + ["O'Brien", r'C:\models\example', 'simple'])
def test_unquoted_target_keeps_literal_embedded_quote(target):
    df=pd.DataFrame({'label':[target,'other']})
    selected=PlotFilters.parse_str('label=='+target).apply(df)
    assert selected['label'].tolist()==[target]

@pytest.mark.parametrize('target', REGRESSIONS[:3])
def test_real_cli_reaches_filter_application_with_literal_target(tmp_path,capsys,target):
    records=[{'label':target,'request_rate':1,'total_token_throughput':100,'median_ttft_ms':10}]
    (tmp_path/'summary.json').write_text(json.dumps(records),encoding='utf8')
    parser=SweepPlotArgs.add_cli_args(FlexibleArgumentParser())
    args=parser.parse_args([str(tmp_path),'--filter-by','label=='+target+',request_rate>1'])
    main(args)
    assert 'No data to plot.' in capsys.readouterr().out
    assert not list(tmp_path.glob('*.png'))
