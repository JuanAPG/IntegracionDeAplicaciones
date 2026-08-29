<?xml version="1.0" encoding="UTF-8"?>
<!--
  =====================================================================
  library/apps/services/soap/library.xsl

  Transformacion XSLT 1.0 que convierte el catalogo library02.xml en una
  interfaz HTML de tarjetas. Se activa desde el propio XML con:

      <?xml-stylesheet type="text/xsl" href="library.xsl"?>

  El navegador aplica la transformacion en el cliente; no hay servidor de
  plantillas ni JavaScript. La presentacion visual la aporta estilo.css,
  compartido con el renderizado directo de library01.xml.

  Por que XSLT y no solo CSS
  * <img> reales: CSS no puede convertir el texto de <image> en imagen,
    XSLT si lo pasa al atributo src.
  * Logica sobre el CONTENIDO: xsl:if test="stock = 0" marca los titulos
    agotados; CSS no puede seleccionar por texto.
  * Agregados: sumas, conteos y el valor del inventario (recursivo).
  * Estructura semantica: article, figure, dl, encabezados jerarquicos.

  Organizacion
    1. Parametros y claves
    2. Plantilla raiz: documento HTML
    3. Cabecera con cifras agregadas
    4. Tarjeta de libro
    5. Bloques multivaluados (autores, generos, conceptos, imagenes)
    6. Utilidades (valor del inventario, moneda)
  =====================================================================
-->
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:lib="urn:library:catalog:1.0"
                exclude-result-prefixes="lib">

  <xsl:output method="html"
              encoding="UTF-8"
              indent="yes"
              doctype-system="about:legacy-compat"/>

  <xsl:strip-space elements="*"/>


  <!-- ===================================================================
       1. CLAVES
       Agrupacion de Muench: para contar autores y generos DISTINTOS,
       XSLT 1.0 no tiene distinct-values(), asi que se indexa por valor y
       se cuenta solo el primer nodo de cada grupo.
       =================================================================== -->
  <xsl:key name="k-author" match="lib:author" use="normalize-space(.)"/>
  <xsl:key name="k-genre"  match="lib:genre"  use="normalize-space(.)"/>


  <!-- ===================================================================
       2. PLANTILLA RAIZ
       =================================================================== -->
  <xsl:template match="/lib:library">
    <html lang="es">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>Catálogo de Libros — <xsl:value-of select="@source"/></title>
        <link rel="stylesheet" href="estilo.css"/>
      </head>
      <body>
        <div class="wrap">
          <xsl:call-template name="hero"/>

          <main class="grid">
            <xsl:apply-templates select="lib:books/lib:book"/>
          </main>

          <footer class="foot">
            <p>
              Fuente <xsl:value-of select="@source"/>
              · esquema <xsl:value-of select="@schema"/>
              · versión <xsl:value-of select="@version"/>
              · generado <xsl:value-of select="@generatedAt"/>
            </p>
            <p>Presentación generada con XSLT 1.0 en el navegador · estilos en estilo.css</p>
          </footer>
        </div>
      </body>
    </html>
  </xsl:template>


  <!-- ===================================================================
       3. CABECERA
       Todas las cifras se derivan del documento; ninguna esta escrita a
       mano, de modo que el encabezado sigue siendo correcto si el XML se
       regenera desde la base de datos.
       =================================================================== -->
  <xsl:template name="hero">
    <header class="hero">
      <p class="hero__eyebrow">
        <xsl:value-of select="@source"/>
        <xsl:text> · esquema </xsl:text><xsl:value-of select="@schema"/>
        <xsl:text> · v</xsl:text><xsl:value-of select="@version"/>
      </p>

      <h1 class="hero__title">Catálogo de Libros</h1>

      <p class="hero__lead">
        Catálogo orientado a libros del servicio SOAP. Cada ficha reúne los
        datos escalares del título junto con sus autores, géneros, conceptos
        definidos e imágenes, tal como se almacenan en la base de datos.
      </p>

      <dl class="hero__stats">
        <div class="stat stat--accent">
          <dt>Títulos</dt>
          <dd><xsl:value-of select="lib:books/@count"/></dd>
        </div>

        <div class="stat">
          <dt>Ejemplares en stock</dt>
          <dd>
            <xsl:value-of select="sum(lib:books/lib:book/lib:stock)"/>
            <span class="stat__unit"> uds.</span>
          </dd>
        </div>

        <div class="stat stat--gold">
          <dt>Valor del inventario</dt>
          <dd>
            <xsl:call-template name="inventory-value">
              <xsl:with-param name="books" select="lib:books/lib:book"/>
            </xsl:call-template>
            <span class="stat__unit"> MXN</span>
          </dd>
        </div>

        <div class="stat stat--alert">
          <dt>Agotados</dt>
          <dd><xsl:value-of select="count(lib:books/lib:book[lib:stock = 0])"/></dd>
        </div>

        <div class="stat">
          <dt>Autores distintos</dt>
          <dd>
            <xsl:value-of select="count(//lib:author[generate-id() =
                                   generate-id(key('k-author', normalize-space(.))[1])])"/>
          </dd>
        </div>

        <div class="stat">
          <dt>Géneros distintos</dt>
          <dd>
            <xsl:value-of select="count(//lib:genre[generate-id() =
                                   generate-id(key('k-genre', normalize-space(.))[1])])"/>
          </dd>
        </div>
      </dl>
    </header>
  </xsl:template>


  <!-- ===================================================================
       4. TARJETA DE LIBRO
       =================================================================== -->
  <xsl:template match="lib:book">
    <!-- Portada: la marcada con isCover; si faltara, la primera imagen. -->
    <xsl:variable name="cover"
                  select="(lib:images/lib:image[@isCover = 'true']
                           | lib:images/lib:image)[1]"/>

    <article class="card">
      <!-- El id de catalogo del formato viaja al HTML para que el CSS
           pueda tenir el filete superior sin repetir la logica. -->
      <xsl:attribute name="data-format">
        <xsl:value-of select="lib:format/@ref"/>
      </xsl:attribute>

      <!-- portada -->
      <xsl:if test="$cover">
        <figure class="cover">
          <img class="cover__img" loading="lazy">
            <xsl:attribute name="src"><xsl:value-of select="normalize-space($cover)"/></xsl:attribute>
            <xsl:attribute name="alt">Portada de <xsl:value-of select="lib:title"/></xsl:attribute>
          </img>
          <xsl:if test="lib:stock = 0">
            <span class="cover__flag">Agotado</span>
          </xsl:if>
        </figure>
      </xsl:if>

      <div class="body">
        <p class="eyebrow">
          N.º <xsl:value-of select="@id"/>
          <xsl:text>   ·   ISBN </xsl:text>
          <xsl:value-of select="@isbn"/>
        </p>

        <h2 class="book-title"><xsl:value-of select="lib:title"/></h2>

        <p class="byline">
          <em>por </em>
          <xsl:apply-templates select="lib:authors/lib:author"/>
        </p>

        <!-- formato y categoria -->
        <ul class="pills">
          <li class="pill pill--format">
            <xsl:attribute name="data-ref"><xsl:value-of select="lib:format/@ref"/></xsl:attribute>
            <xsl:value-of select="lib:format"/>
          </li>
          <li class="pill pill--category"><xsl:value-of select="lib:category"/></li>
        </ul>

        <!-- metricas escalares -->
        <dl class="metrics">
          <div class="metric">
            <dt>Año</dt>
            <dd><xsl:value-of select="lib:publicationYear"/></dd>
          </div>

          <div class="metric metric--price">
            <dt>Precio</dt>
            <dd>
              <xsl:value-of select="format-number(lib:price, '#,##0.00')"/>
              <span class="metric__unit"><xsl:text> </xsl:text>
                <xsl:value-of select="lib:price/@currency"/>
              </span>
            </dd>
          </div>

          <!-- El agotado se decide aqui: XSLT si puede evaluar el texto -->
          <div>
            <xsl:attribute name="class">
              <xsl:text>metric</xsl:text>
              <xsl:if test="lib:stock = 0"> metric--out</xsl:if>
            </xsl:attribute>
            <dt>Stock</dt>
            <dd>
              <xsl:value-of select="lib:stock"/>
              <span class="metric__unit"> uds.</span>
            </dd>
          </div>
        </dl>

        <xsl:apply-templates select="lib:genres[lib:genre]"/>
        <xsl:apply-templates select="lib:concepts[lib:concept]"/>
        <xsl:call-template name="extra-images"/>
      </div>
    </article>
  </xsl:template>


  <!-- ===================================================================
       5. BLOQUES MULTIVALUADOS
       =================================================================== -->

  <!-- libro ->> autor : "por A · B · C" -->
  <xsl:template match="lib:author">
    <xsl:if test="position() != 1">
      <xsl:text>  ·  </xsl:text>
    </xsl:if>
    <xsl:value-of select="."/>
  </xsl:template>

  <!-- libro ->> genero -->
  <xsl:template match="lib:genres">
    <section class="section">
      <h3 class="section__label">Géneros · <xsl:value-of select="@count"/></h3>
      <ul class="chips">
        <xsl:for-each select="lib:genre">
          <li class="chip"><xsl:value-of select="."/></li>
        </xsl:for-each>
      </ul>
    </section>
  </xsl:template>

  <!-- (libro, concepto) -> definicion
       La definicion depende de la clave compuesta, por eso se emite
       dentro del libro y no como dato del catalogo de conceptos. -->
  <xsl:template match="lib:concepts">
    <section class="section">
      <h3 class="section__label">Conceptos · <xsl:value-of select="@count"/></h3>
      <dl class="concepts">
        <xsl:for-each select="lib:concept">
          <dt><xsl:value-of select="lib:name"/></dt>
          <dd><xsl:value-of select="lib:definition"/></dd>
        </xsl:for-each>
      </dl>
    </section>
  </xsl:template>

  <!-- libro ->> imagen : solo las que NO son portada, para no repetir la
       que ya encabeza la tarjeta. -->
  <xsl:template name="extra-images">
    <xsl:variable name="extra" select="lib:images/lib:image[not(@isCover = 'true')]"/>
    <xsl:if test="$extra">
      <section class="section">
        <h3 class="section__label">Otras imágenes · <xsl:value-of select="count($extra)"/></h3>
        <ul class="thumbs">
          <xsl:for-each select="$extra">
            <li>
              <a target="_blank" rel="noopener">
                <xsl:attribute name="href"><xsl:value-of select="normalize-space(.)"/></xsl:attribute>
                <img loading="lazy">
                  <xsl:attribute name="src"><xsl:value-of select="normalize-space(.)"/></xsl:attribute>
                  <xsl:attribute name="alt">Imagen <xsl:value-of select="@id"/> de <xsl:value-of select="../../lib:title"/></xsl:attribute>
                </img>
              </a>
            </li>
          </xsl:for-each>
        </ul>
      </section>
    </xsl:if>
  </xsl:template>


  <!-- ===================================================================
       6. UTILIDADES
       =================================================================== -->

  <!-- Valor del inventario = suma de precio * stock.
       XSLT 1.0 solo sabe sumar nodos con sum(); un producto por libro
       exige recorrer la lista de forma recursiva. -->
  <xsl:template name="inventory-value">
    <xsl:param name="books"/>
    <xsl:param name="acc" select="0"/>
    <xsl:choose>
      <xsl:when test="$books">
        <xsl:call-template name="inventory-value">
          <xsl:with-param name="books" select="$books[position() &gt; 1]"/>
          <xsl:with-param name="acc"
                          select="$acc + ($books[1]/lib:price * $books[1]/lib:stock)"/>
        </xsl:call-template>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="format-number($acc, '#,##0.00')"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

</xsl:stylesheet>
