"""Synthetic native TSV; only the three reference SA numbers come from the task spec."""
from pathlib import Path
import json


def native_text():
    lines=['cbsa\tmetro_name\tyr\tqtr\tindex_nsa\tindex_sa']
    # Exactly 142 consecutive synthetic Austin quarters, 1991Q1 through 2026Q2.
    for i in range(142):
        year,quarter=1991+i//4,i%4+1
        sa={(2025,4):680.77,(2026,1):656.56,(2026,2):681.16}.get((year,quarter),100+i*4)
        nsa=693.01 if (year,quarter)==(2026,2) else sa+5
        lines.append(f'12420\t"Austin-Round Rock-San Marcos, TX"\t{year}\t{quarter}\t{nsa:.2f}\t{sa:.2f}')
    # Other metros can have unavailable indexes; never parse their numeric cells.
    lines.append('99999\t"Synthetic Metro, XX"\t2026\t2\t.\t.')
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    (Path(__file__).parent/'fixtures/austin_hpi.json').write_text(json.dumps({'status':200,'body':native_text()},indent=2)+'\n')
