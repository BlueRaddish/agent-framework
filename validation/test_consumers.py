"""Independent public parser consumers: decimals, nested dispatch and JSON options."""
import json
import pytest
from vllm.utils.argparse_utils import FlexibleArgumentParser


def make_parser(nested=False):
    root = FlexibleArgumentParser()
    parser = root
    if nested:
        parser = root.add_subparsers().add_parser('bench')
        parser = parser.add_subparsers().add_parser('serve')
    parser.add_argument('--frequency-penalty', type=float)
    parser.add_argument('--batch-size', type=int)
    parser.add_argument('--hf-overrides', type=json.loads)
    return root


@pytest.mark.parametrize('value', ['-0.5', '-.5', '-1.25', '-0.0'])
@pytest.mark.parametrize('layout', ['before-control', 'last', 'nested'])
def test_negative_decimal_public_consumer(value, layout):
    """Separate numeric values survive preprocessing and subcommand dispatch."""
    nested = layout == 'nested'
    argv = ['bench', 'serve'] if nested else []
    if layout == 'last':
        argv += ['--batch-size', '7', '--frequency-penalty', value]
    else:
        argv += ['--frequency-penalty', value, '--batch-size', '7']
    parsed = make_parser(nested).parse_args(argv)
    assert parsed.frequency_penalty == float(value)
    assert parsed.batch_size == 7


@pytest.mark.parametrize('argv,expected', [
    (['--frequency-penalty=-0.5'], (-0.5, None)),
    (['--frequency_penalty', '-2'], (-2.0, None)),
    (['--hf-overrides.temperature', '-0.5'], (None, {'temperature': -0.5})),
    (['--hf-overrides.tags+', 'a', '--hf-overrides.tags+', 'b'],
     (None, {'tags': ['a', 'b']})),
])
def test_unchanged_public_parser_controls(argv, expected):
    parsed = make_parser().parse_args(argv)
    assert (parsed.frequency_penalty, parsed.hf_overrides) == expected
