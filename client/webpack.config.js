const fs = require('fs');
const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const HtmlWebpackPlugin = require('html-webpack-plugin');

const viewsDir = path.resolve(process.cwd(), 'views');
const views = fs.readdirSync(viewsDir);

module.exports = {
  entry: function() {
    const entries = {};

    for (const view of views) {
      entries[view] = path.resolve(viewsDir, view, 'app.js');
    }

    return entries;
  }(),

  module: {
    rules: [
      {
        test: /\.jsx?$/,
        use: {
          loader: 'babel-loader',
          options: {
            plugins: [
              ['@babel/plugin-transform-react-jsx', { runtime: 'classic', pragma: 'm' }]
            ]
          }
        }
      },
      {
        test: /\.scss$/,
        use: [
          { loader: MiniCssExtractPlugin.loader },
          'css-loader',
          {
            loader: 'sass-loader',
            options: {
              sassOptions: {
                silenceDeprecations: ['import', 'global-builtin', 'color-functions', 'slash-div']
              }
            }
          }
        ]
      },
      {
        test:  /\.(png|jpg|gif|svg|woff2)$/,
        type: 'asset/resource',
        generator: {
          filename: 'assets/[hash][ext]'
        }
      }
    ]
  },

  output: {
    filename: '[name].js',
    path: path.resolve(process.cwd(), 'dist'),
    publicPath: '',
    library: { type: 'window' }
  },

  plugins: [
    new MiniCssExtractPlugin({
      filename: '[name].css'
    }),
    ...views.map(view => {
      let templatePath = path.resolve(viewsDir, view, 'app.html');
      if (!fs.existsSync(templatePath))
        templatePath = path.resolve(__dirname, 'common', 'App.html');

      return new HtmlWebpackPlugin({
        filename: view + '.html',
        template: templatePath,
        excludeChunks: views.filter(excludedView => excludedView !== view),
        inject: false,
        // The shared template iterates htmlWebpackPlugin.files.{css,chunks}, which html-webpack-plugin 4+ no longer provides
        templateParameters: (compilation, assets, assetTags, options) => ({
          compilation,
          webpackConfig: compilation.options,
          htmlWebpackPlugin: {
            tags: assetTags,
            files: {
              css: assets.css,
              chunks: assets.js.map(entry => ({ entry }))
            },
            options
          }
        })
      })
    })
  ]
};
