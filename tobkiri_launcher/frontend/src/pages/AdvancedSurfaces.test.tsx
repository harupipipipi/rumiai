import assert from 'node:assert/strict';
import test from 'node:test';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router';

import {AiInput} from './AiInput';
import {ApiMap} from './ApiMap';
import {Flow} from './Flow';
import {Graph} from './Graph';
import {NodeManager} from './NodeManager';
import {Profile} from './Profile';
import {ProfileFiles} from './ProfileFiles';
import {ProfileWiring} from './ProfileWiring';
import {Settings} from './Settings';
import {LAUNCHER_ADVANCED_VIEWS} from '@/src/lib/advancedSurfaces';
import {useAppStore} from '@/src/store';

const routePages = [
  ['profile', Profile],
  ['settings', Settings],
  ['profileWiring', ProfileWiring],
  ['profileFiles', ProfileFiles],
  ['flow', Flow],
  ['graph', Graph],
  ['aiInput', AiInput],
  ['apiMap', ApiMap],
  ['nodeManager', NodeManager],
] as const;

function assertRenderedLabel(html: string, label: string): void {
  // renderToStaticMarkup escapes text nodes; assert the serialized DOM value
  // without changing the product copy or treating `&` as a regexp token.
  const serializedLabel = label.replaceAll('&', '&amp;');
  assert.ok(html.includes(serializedLabel), `missing surface label: ${label}`);
}

test('every restored Advanced route renders its named v4 surface and explicit support status', () => {
  const previousState = useAppStore.getState();
  useAppStore.setState({packs: [], packsLoading: false});
  try {
    for (const [id, Page] of routePages) {
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/']}>
          <Page />
        </MemoryRouter>,
      );
      assertRenderedLabel(html, LAUNCHER_ADVANCED_VIEWS[id].label);
      assert.match(html, /Partial|Mapped|Rebuilt|Launcher local/);
      assert.doesNotMatch(html, /runtime-recovery|Recovery|GraphEditor|aiInputGraph/);
    }
  } finally {
    useAppStore.setState(previousState, true);
  }
});

test('Graph and Profile Wiring state the unavailable v4 operation and provide the Profile ceremony path', () => {
  const graph = renderToStaticMarkup(<MemoryRouter><Graph /></MemoryRouter>);
  const wiring = renderToStaticMarkup(<MemoryRouter><ProfileWiring /></MemoryRouter>);
  assert.match(graph, /v4 operation is not provided/);
  assert.match(wiring, /v4 operation is not provided/);
  assert.match(graph + wiring, /Profile projection|Profile ceremony/);
});
