import './Camo.scss';
import * as m from 'mithril';
import App from '../common/App';
import CamoResourcesOverview from './components/CamoResourcesOverview';
import CamoHeroesOverview from './components/CamoHeroesOverview';

export default class CamoVersusApp extends App {
  view() {
    return [
      this.settings.showResources ? <CamoResourcesOverview /> : null,
      this.settings.showHeroes ? <CamoHeroesOverview /> : null
    ];
  }
}
